import { useState, useCallback, useEffect, useRef } from 'react'
import { Pencil, Trash2, FolderInput, Eraser, Trash } from 'lucide-react'
import { FolderListSidebar } from '../components/shared/FolderListSidebar'
import { RenameDialog } from '../components/shared/RenameDialog'
import { MoveFolderDialog } from '../components/shared/MoveFolderDialog'
import { MessageList } from '../components/chat/MessageList'
import { ChatInput } from '../components/chat/ChatInput'
import { RetrievalPanel } from '../components/chat/RetrievalPanel'
import { ResizablePanel } from '../components/ui/ResizablePanel'
import { EmptyState } from '../components/ui/EmptyState'
import { useConversations } from '../hooks/useConversations'
import { useMessages } from '../hooks/useMessages'
import { useStreamingChat } from '../hooks/useStreamingChat'
import type { ChunkInfo } from '../hooks/useStreamingChat'
import { useFolders } from '../hooks/useFolders'
import { useSettings } from '../contexts/SettingsContext'
import { useToast } from '../contexts/ToastContext'
import { conversationsService } from '../services/conversations'
import type { ConversationOut } from '../types/conversation'
import type { ChatMessage as ChatMessageType } from '../types/chat'
import { formatRelativeTime } from '../utils/format'
import { MessageSquare } from 'lucide-react'
import { useI18n } from '../i18n'

export function ChatPage() {
  const { conversations, create, update, remove, search } = useConversations()
  const { folders, createFolder, renameFolder, deleteFolder } = useFolders('conversations')
  const { streamOutputEnabled } = useSettings()
  const toast = useToast()
  const { t } = useI18n()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [modelId, setModelId] = useState<number | null>(null)
  const [kbIds, setKbIds] = useState<number[]>([])
  const [citationStyle, setCitationStyle] = useState('apa')
  const [panelCollapsed, setPanelCollapsed] = useState(true)
  const [highlightedChunk, setHighlightedChunk] = useState<number | null>(null)
  // Persisted chunks — rebuilt from loaded messages, updated after each streaming turn
  const [storedChunks, setStoredChunks] = useState<ChunkInfo[]>([])

  // Rename / move-to-folder dialog state
  const [renamingConv, setRenamingConv] = useState<ConversationOut | null>(null)
  const [movingConvId, setMovingConvId] = useState<number | null>(null)
  const [renamingFolder, setRenamingFolder] = useState<import('../types/folder').Folder | null>(null)

  const { messages, load: loadMessages, addLocal, removeMessage, editAndTruncate, clear: clearMessages } = useMessages(selectedId)
  const streaming = useStreamingChat()

  // Rebuild stored chunks from ALL messages' references when messages change
  // (covers conversation switch, new messages loaded from DB, etc.)
  useEffect(() => {
    const seen = new Set<number>()
    const chunks: ChunkInfo[] = []
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.references) {
        for (const ref of msg.references) {
          if (!seen.has(ref.ref_num)) {
            seen.add(ref.ref_num)
            chunks.push({
              document_id: ref.document_file_id,
              original_filename: ref.original_filename,
              chunk_index: ref.ref_num,
              content: ref.chunk_content || ref.formatted_citation,
              score: ref.score ?? 0,
              formatted_citation: ref.formatted_citation,
              kb_id: ref.knowledge_base_id,
            })
          }
        }
      }
    }
    setStoredChunks(chunks)
  }, [messages])

  const handleNewConversation = useCallback(async () => {
    try {
      const conv = await create({ title: t('chat.new_conversation'), model_id: modelId, kb_ids: kbIds.length > 0 ? kbIds : undefined })
      setSelectedId(conv.id)
    } catch {
      toast.error(t('chat.create_failed'))
    }
  }, [create, modelId, kbIds, toast, t])

  const handleSelect = useCallback((conv: ConversationOut) => {
    setSelectedId(conv.id)
    setModelId(conv.model_id)
    setKbIds(conv.kb_ids ?? [])
    setCitationStyle(conv.citation_style || 'apa')
    // Default to collapsed — panel shows as a thin bar on the right;
    // user can expand to see full retrieval results
    setPanelCollapsed(true)
  }, [])

  const handleSend = useCallback(async (content: string) => {
    if (!selectedId || !modelId) {
      toast.warning(t('chat.select_conversation_model_first'))
      return
    }

    // Add user message locally
    const userMsg = {
      id: Date.now(),
      conversation_id: selectedId,
      role: 'user' as const,
      content,
      position: messages.length,
      references: null,
      created_at: new Date().toISOString()
    }
    addLocal(userMsg)

    // Don't add assistant placeholder — the MessageList streaming block handles it

    const allMessages: ChatMessageType[] = []
    
    // Default prompt for RAG to avoid hallucination
    if (kbIds.length > 0) {
      allMessages.push({ 
        role: 'system', 
        content: '你是一个知识库问答助手。请基于检索到的知识库内容来回答用户的问题，对检索结果进行分析、归纳和总结。只有在检索结果与问题完全无关时，才回答"根据已知信息无法回答该问题"。不要编造知识库中没有的信息。' 
      })
    }

    allMessages.push(
      ...messages.map((m) => ({ role: m.role, content: m.content })),
      { role: 'user' as const, content }
    )

    const options = kbIds.length > 0
      ? {
          kb_ids: kbIds,
          conversation_id: selectedId,
          citation_style: citationStyle,
          existing_references: messages
            .filter(m => m.role === 'assistant' && m.references)
            .flatMap(m => m.references!.map(r => ({
              ref_num: r.ref_num,
              document_file_id: r.document_file_id,
              original_filename: r.original_filename,
              formatted_citation: r.formatted_citation
            })))
        }
      : undefined

    streaming.send(allMessages, modelId, options, selectedId, streamOutputEnabled)
    if (kbIds.length > 0) setPanelCollapsed(false)
  }, [selectedId, modelId, kbIds, messages, citationStyle, addLocal, streaming, streamOutputEnabled, toast, t])

  // Persist the final assistant message when a turn finishes
  const prevStreamingRef = useRef(false)
  useEffect(() => {
    if (prevStreamingRef.current && !streaming.isStreaming && selectedId) {
      if (!streaming.error) {
        if (streaming.currentResponse) {
          const refs = streaming.citations?.references ?? null
          // Add locally for immediate display
          addLocal({
            id: Date.now(),
            conversation_id: selectedId,
            role: 'assistant',
            content: streaming.currentResponse,
            position: messages.length,
            references: refs,
            created_at: new Date().toISOString()
          })
        }

        // Accumulate fresh chunks into stored chunks
        if (streaming.retrievedChunks.length > 0) {
          setStoredChunks(prev => {
            const seen = new Set(prev.map(c => c.chunk_index))
            const merged = [...prev]
            for (const chunk of streaming.retrievedChunks) {
              if (!seen.has(chunk.chunk_index)) {
                seen.add(chunk.chunk_index)
                merged.push(chunk)
              }
            }
            return merged
          })
        }

        // Always reload from DB to get real IDs (deletable) and authoritative content
        loadMessages()

        if (!streaming.currentResponse && (!streaming.citations || streaming.citations.references.length === 0)) {
          toast.warning(t('chat.empty_response'))
        }
      }
    }
    prevStreamingRef.current = streaming.isStreaming
  }, [
    streaming.isStreaming,
    streaming.currentResponse,
    streaming.citations,
    streaming.error,
    selectedId,
    addLocal,
    loadMessages,
    messages.length,
    toast,
    t
  ])

  useEffect(() => {
    if (streaming.error) {
      toast.error(streaming.error)
    }
  }, [streaming.error, toast])

  const handleDeleteMessage = useCallback(async (msgId: number) => {
    try {
      await removeMessage(msgId)
    } catch {
      toast.error(t('chat.delete_message_failed'))
    }
  }, [removeMessage, toast, t])

  const handleEditMessage = useCallback(async (msgId: number, newContent: string) => {
    if (!selectedId || !modelId) return
    try {
      await editAndTruncate(msgId, newContent)
      // Re-send the edited message to get a new response
      const updatedMessages = messages.filter(m => {
        const target = messages.find(mm => mm.id === msgId)
        return target ? m.position <= target.position : true
      })
      // Replace the content of the edited message
      const allMsgs: ChatMessageType[] = []
      if (kbIds.length > 0) {
        allMsgs.push({
          role: 'system',
          content: '你是一个知识库问答助手。请基于检索到的知识库内容来回答用户的问题，对检索结果进行分析、归纳和总结。只有在检索结果与问题完全无关时，才回答"根据已知信息无法回答该问题"。不要编造知识库中没有的信息。'
        })
      }
      for (const m of updatedMessages) {
        if (m.id === msgId) {
          allMsgs.push({ role: m.role, content: newContent })
        } else {
          allMsgs.push({ role: m.role, content: m.content })
        }
      }
      const options = kbIds.length > 0
        ? { kb_ids: kbIds, conversation_id: selectedId, citation_style: citationStyle, existing_references: [] }
        : undefined
      streaming.send(allMsgs, modelId, options, selectedId, streamOutputEnabled)
      if (kbIds.length > 0) setPanelCollapsed(false)
    } catch {
      toast.error(t('chat.edit_failed'))
    }
  }, [selectedId, modelId, kbIds, messages, citationStyle, editAndTruncate, streaming, streamOutputEnabled, toast, t])

  const handleRegenerateMessage = useCallback(async (msgId: number) => {
    if (!selectedId || !modelId) return
    try {
      // Find the assistant message and the preceding user message
      const msgIndex = messages.findIndex(m => m.id === msgId)
      if (msgIndex < 0) return
      // Delete the assistant message
      await removeMessage(msgId)
      // Build messages up to the one before this assistant message
      const historyMessages = messages.slice(0, msgIndex)
      const allMsgs: ChatMessageType[] = []
      if (kbIds.length > 0) {
        allMsgs.push({
          role: 'system',
          content: '你是一个知识库问答助手。请基于检索到的知识库内容来回答用户的问题，对检索结果进行分析、归纳和总结。只有在检索结果与问题完全无关时，才回答"根据已知信息无法回答该问题"。不要编造知识库中没有的信息。'
        })
      }
      allMsgs.push(...historyMessages.map(m => ({ role: m.role, content: m.content })))
      const existingRefs = historyMessages
        .filter(m => m.role === 'assistant' && m.references)
        .flatMap(m => m.references!.map(r => ({
          ref_num: r.ref_num,
          document_file_id: r.document_file_id,
          original_filename: r.original_filename,
          formatted_citation: r.formatted_citation
        })))
      const options = kbIds.length > 0
        ? { kb_ids: kbIds, conversation_id: selectedId, citation_style: citationStyle, existing_references: existingRefs }
        : undefined
      streaming.send(allMsgs, modelId, options, selectedId, streamOutputEnabled)
      if (kbIds.length > 0) setPanelCollapsed(false)
    } catch {
      toast.error(t('chat.regenerate_failed'))
    }
  }, [selectedId, modelId, kbIds, messages, citationStyle, removeMessage, streaming, streamOutputEnabled, toast, t])

  const handleClearMessages = useCallback(async () => {
    try {
      await clearMessages()
      toast.success(t('chat.messages_cleared'))
    } catch {
      toast.error(t('chat.clear_messages_failed'))
    }
  }, [clearMessages, toast, t])

  const handleClearAllConversations = useCallback(async () => {
    try {
      await conversationsService.removeAll()
      setSelectedId(null)
      window.location.reload()
    } catch {
      toast.error(t('chat.clear_conversations_failed'))
    }
  }, [toast, t])

  const handleRenameConvConfirm = useCallback(async (name: string) => {
    if (!renamingConv) return
    try {
      await update(renamingConv.id, { title: name })
    } catch {
      toast.error(t('common.rename_failed'))
    }
  }, [renamingConv, update, toast, t])

  const handleMoveConvConfirm = useCallback(async (folderId: string | null) => {
    if (movingConvId === null) return
    try {
      await update(movingConvId, { folder_id: folderId ? Number(folderId) : null })
    } catch {
      toast.error(t('common.move_failed'))
    }
  }, [movingConvId, update, toast, t])

  const handleRenameFolderConfirm = useCallback(async (name: string) => {
    if (!renamingFolder) return
    try {
      await renameFolder(renamingFolder.id, name)
    } catch {
      toast.error(t('chat.rename_folder_failed'))
    }
  }, [renamingFolder, renameFolder, toast, t])

  const handleDragMoveToFolder = useCallback(async (itemId: string | number, folderId: string | null) => {
    try {
      await update(Number(itemId), { folder_id: folderId ? Number(folderId) : null })
    } catch {
      toast.error(t('common.move_failed'))
    }
  }, [update, toast, t])

  const handleCiteClick = (refNum: number) => {
    setHighlightedChunk(refNum)
    setPanelCollapsed(false)
  }

  // Merge stored chunks from previous turns with live streaming chunks
  const displayChunks = (() => {
    if (!streaming.isStreaming && streaming.retrievedChunks.length === 0) return storedChunks
    // Merge: stored first, then new streaming chunks (dedup by chunk_index)
    const seen = new Set(storedChunks.map(c => c.chunk_index))
    const merged = [...storedChunks]
    for (const chunk of streaming.retrievedChunks) {
      if (!seen.has(chunk.chunk_index)) {
        seen.add(chunk.chunk_index)
        merged.push(chunk)
      }
    }
    return merged
  })()

  const selected = conversations.find((c) => c.id === selectedId)

  return (
    <>
    <div className="flex h-full">
      <ResizablePanel defaultWidth={260} minWidth={200} maxWidth={400} storageKey="chat_sidebar_width">
        <FolderListSidebar
          items={conversations}
          folders={folders}
          selectedId={selectedId}
          onSelect={handleSelect}
          onCreateNew={handleNewConversation}
          onSearch={search}
          renderItem={(conv) => (
            <div className="flex flex-col min-w-0">
              <span className="truncate">{conv.summary || conv.title}</span>
              <span className="text-xs text-neutral-500 truncate">
                {formatRelativeTime(conv.updated_at)}
              </span>
            </div>
          )}
          title={t('nav.chat')}
          createLabel={t('chat.new_chat')}
          searchPlaceholder={t('chat.search_chats')}
          getItemFolder={(id) => {
            const conv = conversations.find((c) => c.id === id)
            return conv?.folder_id ? String(conv.folder_id) : null
          }}
          getContextMenuItems={(conv) => [
            { label: t('common.rename'), icon: <Pencil className="h-4 w-4" />, onClick: () => setRenamingConv(conv) },
            { label: t('common.move_to_folder'), icon: <FolderInput className="h-4 w-4" />, onClick: () => setMovingConvId(conv.id) },
            { label: t('chat.clear_messages'), icon: <Eraser className="h-4 w-4" />, onClick: () => { if (conv.id === selectedId) handleClearMessages() } },
            { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => remove(conv.id), danger: true }
          ]}
          headerActions={
            <button
              onClick={handleClearAllConversations}
              className="p-1 rounded text-neutral-400 hover:text-red-400 hover:bg-white/10 transition"
              title={t('chat.clear_all')}
            >
              <Trash className="h-4 w-4" />
            </button>
          }
          getFolderContextMenuItems={(folder) => [
            { label: t('common.rename'), icon: <Pencil className="h-4 w-4" />, onClick: () => setRenamingFolder(folder) },
            { label: t('common.delete_folder'), icon: <Trash2 className="h-4 w-4" />, onClick: () => deleteFolder(folder.id), danger: true }
          ]}
          onCreateFolder={() => createFolder(t('common.new_folder'))}
          onMoveToFolder={handleDragMoveToFolder}
        />
      </ResizablePanel>

      {selected ? (
        <>
          <div className="flex-1 flex flex-col min-w-0 pb-2">
            <MessageList
              messages={messages}
              streamingContent={streaming.isStreaming ? streaming.currentResponse : undefined}
              isStreaming={streaming.isStreaming}
              isSearching={streaming.isSearching}
              searchQuery={streaming.searchQuery}
              streamingReferences={streaming.citations?.references ?? null}
              onCiteClick={handleCiteClick}
              onDeleteMessage={handleDeleteMessage}
              onEditMessage={handleEditMessage}
              onRegenerateMessage={handleRegenerateMessage}
            />
            <div className="mt-auto">
              <ChatInput
                modelId={modelId}
                onModelChange={setModelId}
                kbIds={kbIds}
                onKBChange={setKbIds}
                citationStyle={citationStyle}
                onCitationStyleChange={setCitationStyle}
                onSend={handleSend}
                onAbort={streaming.abort}
                isStreaming={streaming.isStreaming}
              />
            </div>
          </div>
          {(kbIds.length > 0 || displayChunks.length > 0) && !panelCollapsed && (
            <ResizablePanel defaultWidth={340} minWidth={260} maxWidth={500} side="right" storageKey="chat_retrieval_panel_width">
              <RetrievalPanel
                chunks={displayChunks}
                collapsed={panelCollapsed}
                onToggle={() => setPanelCollapsed(!panelCollapsed)}
                highlightedChunk={highlightedChunk}
              />
            </ResizablePanel>
          )}
          {(kbIds.length > 0 || displayChunks.length > 0) && panelCollapsed && (
            <div className="shrink-0 bg-neutral-50/50 dark:bg-black/20">
              <RetrievalPanel
                chunks={displayChunks}
                collapsed={panelCollapsed}
                onToggle={() => setPanelCollapsed(!panelCollapsed)}
                highlightedChunk={highlightedChunk}
              />
            </div>
          )}
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={<MessageSquare className="h-12 w-12" />}
            title={t('chat.empty_title')}
            description={t('chat.empty_desc')}
            action={{ label: t('chat.new_chat'), onClick: handleNewConversation }}
          />
        </div>
      )}
    </div>

    {/* Rename conversation dialog */}
    <RenameDialog
      open={!!renamingConv}
      onOpenChange={(v) => { if (!v) setRenamingConv(null) }}
      title={t('chat.rename_chat')}
      initialValue={renamingConv?.title ?? ''}
      onConfirm={handleRenameConvConfirm}
    />

    {/* Move conversation to folder dialog */}
    <MoveFolderDialog
      open={movingConvId !== null}
      onOpenChange={(v) => { if (!v) setMovingConvId(null) }}
      folders={folders}
      currentFolderId={(() => {
        const conv = conversations.find((c) => c.id === movingConvId)
        return conv?.folder_id ? String(conv.folder_id) : null
      })()}
      onConfirm={handleMoveConvConfirm}
    />

    {/* Rename folder dialog */}
    <RenameDialog
      open={!!renamingFolder}
      onOpenChange={(v) => { if (!v) setRenamingFolder(null) }}
      title={t('common.rename_folder')}
      initialValue={renamingFolder?.name ?? ''}
      onConfirm={handleRenameFolderConfirm}
    />
  </>
  )
}
