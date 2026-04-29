import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
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
import { modelsService } from '../services/models'
import { knowledgeService } from '../services/knowledge'
import type { ConversationOut } from '../types/conversation'
import type { ChatMessage as ChatMessageType } from '../types/chat'
import type { AIModelOut } from '../types/provider'
import type { KnowledgeBaseOut } from '../types/knowledge'
import { formatRelativeTime } from '../utils/format'
import { MessageSquare } from 'lucide-react'
import { useI18n } from '../i18n'
import type { ReferenceItem } from '../types/conversation'
import { buildGlobalCitationRemapping } from '../utils/citationRemap'

function normalizeReferenceChunks(references: ReferenceItem[]): ChunkInfo[] {
  const chunks: ChunkInfo[] = []
  const seen = new Set<string>()

  for (const ref of references) {
    const nestedChunks = ref.chunks && ref.chunks.length > 0
      ? ref.chunks
      : [{
          chunk_index: ref.chunk_index ?? ref.ref_num,
          chunk_content: ref.chunk_content || ref.formatted_citation,
          knowledge_base_id: ref.knowledge_base_id,
          score: ref.score,
        }]

    for (const chunk of nestedChunks) {
      const chunkKey = `${ref.document_file_id}:${chunk.chunk_index}:${chunk.chunk_content}`
      if (seen.has(chunkKey)) continue
      seen.add(chunkKey)

      chunks.push({
        chunk_key: chunkKey,
        citation_num: ref.ref_num,
        document_id: ref.document_file_id,
        original_filename: ref.original_filename,
        chunk_index: chunk.chunk_index,
        content: chunk.chunk_content || ref.formatted_citation,
        score: chunk.score ?? ref.score ?? 0,
        formatted_citation: ref.formatted_citation,
        kb_id: chunk.knowledge_base_id ?? ref.knowledge_base_id,
      })
    }
  }

  return chunks
}

export function ChatPage() {
  const { conversations, create, update, remove, search, load: loadConversations } = useConversations()
  const { folders, createFolder, renameFolder, deleteFolder } = useFolders('conversations')
  const { settings, streamOutputEnabled } = useSettings()
  const toast = useToast()
  const { t } = useI18n()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [modelId, setModelId] = useState<number | null>(null)
  const [kbIds, setKbIds] = useState<number[]>([])
  const [panelCollapsed, setPanelCollapsed] = useState(true)
  const [highlightedChunkKey, setHighlightedChunkKey] = useState<string | null>(null)
  // Persisted chunks — rebuilt from loaded messages, updated after each streaming turn
  const [storedChunks, setStoredChunks] = useState<ChunkInfo[]>([])

  // Rename / move-to-folder dialog state
  const [renamingConv, setRenamingConv] = useState<ConversationOut | null>(null)
  const [movingConvId, setMovingConvId] = useState<number | null>(null)
  const [renamingFolder, setRenamingFolder] = useState<import('../types/folder').Folder | null>(null)
  const summaryRefreshTimersRef = useRef<number[]>([])

  const createTempMessageId = useCallback(() => {
    // Use negative IDs for local-only messages so they are never mistaken for DB records.
    return -(Date.now() + Math.floor(Math.random() * 1000))
  }, [])

  const { messages, load: loadMessages, addLocal, removeMessage, editAndTruncate, clear: clearMessages } = useMessages(selectedId)
  const streaming = useStreamingChat()
  const citationStyle = settings?.chat_citation_style ?? 'apa'
  const citationMode = (settings?.chat_citation_mode ?? 'document') as 'document' | 'chunk'
  const isStreamingForSelected = !!selectedId && streaming.isStreaming && streaming.conversationId === selectedId

  // Models list — fetched once, used to resolve model name/provider for display
  const [chatModels, setChatModels] = useState<AIModelOut[]>([])
  const [allKbs, setAllKbs] = useState<KnowledgeBaseOut[]>([])
  useEffect(() => {
    modelsService.list({ model_type: 'chat' }).then(setChatModels).catch(console.error)
    knowledgeService.list().then(setAllKbs).catch(console.error)
  }, [])

  // Current conversation model info — derived from the live modelId selection.
  const currentModelInfo = useMemo(() => {
    const id = modelId ?? conversations.find(c => c.id === selectedId)?.model_id
    const m = chatModels.find(m => m.id === id)
    if (!m) return undefined
    return { name: m.display_name || m.api_name, provider: m.provider_name }
  }, [modelId, conversations, selectedId, chatModels])

  // Keep model selection stable across conversation list refreshes.
  const handleModelChange = useCallback((id: number | null) => {
    setModelId(id)
    if (selectedId && id != null) {
      void update(selectedId, { model_id: id }).catch((err) => {
        console.error('Failed to persist conversation model', err)
      })
    }
  }, [selectedId, update])

  // Build a global local->display mapping so the retrieval panel numbering
  // is aligned with the same remapped citation numbers shown in chat messages.
  const globalLocalToDisplay = useMemo(() => {
    const remapping = buildGlobalCitationRemapping(
      messages
        .filter((m) => m.role === 'assistant')
        .map((m) => ({ id: m.id, references: m.references })),
      isStreamingForSelected ? (streaming.citations?.references ?? null) : null,
      citationMode
    )

    const merged = new Map<number, number>()
    for (const mapItem of remapping.values()) {
      for (const [local, display] of mapItem.localToDisplay.entries()) {
        if (!merged.has(local)) {
          merged.set(local, display)
        }
      }
    }
    return merged
  }, [messages, streaming.citations, citationMode, isStreamingForSelected])

  const clearSummaryRefreshTimers = useCallback(() => {
    for (const timer of summaryRefreshTimersRef.current) {
      window.clearTimeout(timer)
    }
    summaryRefreshTimersRef.current = []
  }, [])

  const scheduleConversationRefresh = useCallback(() => {
    clearSummaryRefreshTimers()
    void loadConversations()
    const refreshDelays = [2000, 5000, 10000, 20000, 35000]
    summaryRefreshTimersRef.current = refreshDelays.map((delay) => (
      window.setTimeout(() => { void loadConversations() }, delay)
    ))
  }, [clearSummaryRefreshTimers, loadConversations])

  useEffect(() => clearSummaryRefreshTimers, [clearSummaryRefreshTimers])

  // Rebuild stored chunks from ALL messages' references when messages change
  // (covers conversation switch, new messages loaded from DB, etc.)
  useEffect(() => {
    const seen = new Set<string>()
    const chunks: ChunkInfo[] = []
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.references) {
        for (const chunk of normalizeReferenceChunks(msg.references)) {
          if (seen.has(chunk.chunk_key)) {
            continue
          }
          seen.add(chunk.chunk_key)
          chunks.push(chunk)
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
    // Keep streaming in background; only the owning conversation renders stream UI.
    setSelectedId(conv.id)
    setModelId(conv.model_id)
    setKbIds(conv.kb_ids ?? [])
    // Default to collapsed — panel shows as a thin bar on the right;
    // user can expand to see full retrieval results
    setPanelCollapsed(true)
  }, [])

  const handleSend = useCallback(async (content: string) => {
    const effectiveModelId = modelId ?? chatModels.find(m => m.is_enabled)?.id ?? null

    if (!selectedId || !effectiveModelId) {
      toast.warning(t('chat.select_conversation_model_first'))
      return
    }

    if (modelId == null) {
      setModelId(effectiveModelId)
      void update(selectedId, { model_id: effectiveModelId }).catch((err) => {
        console.error('Failed to persist fallback conversation model', err)
      })
    }

    clearSummaryRefreshTimers()

    // Add user message locally
    const userMsg = {
      id: createTempMessageId(),
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
              formatted_citation: r.formatted_citation,
              chunk_index: r.chunk_index,
              chunk_content: r.chunk_content,
              knowledge_base_id: r.knowledge_base_id,
              score: r.score,
              chunks: r.chunks ?? []
            })))
        }
      : undefined

    streaming.send(allMessages, effectiveModelId, options, selectedId, streamOutputEnabled)
    if (kbIds.length > 0) setPanelCollapsed(false)
  }, [selectedId, modelId, chatModels, kbIds, messages, citationStyle, addLocal, clearSummaryRefreshTimers, streaming, streamOutputEnabled, update, toast, t, createTempMessageId])

  // Persist the final assistant message when a turn finishes
  const prevStreamingRef = useRef(false)
  useEffect(() => {
    const completedConversationId = streaming.conversationId
    if (prevStreamingRef.current && !streaming.isStreaming && completedConversationId) {
      const isCompletedConversationSelected = selectedId === completedConversationId
      if (!streaming.error) {
        if (streaming.currentResponse && isCompletedConversationSelected) {
          const refs = streaming.citations?.references ?? null
          // Add locally for immediate display
          const localAssistantMsg: import('../types/conversation').MessageOut = {
            id: createTempMessageId(),
            conversation_id: completedConversationId,
            role: 'assistant',
            content: streaming.currentResponse,
            position: messages.length,
            references: refs,
            model_id: streaming.modelId ?? undefined,
            created_at: new Date().toISOString()
          }
          addLocal(localAssistantMsg)

          // Accumulate fresh chunks into stored chunks
          if (streaming.retrievedChunks.length > 0 && isCompletedConversationSelected) {
            setStoredChunks(prev => {
              const seen = new Set(prev.map(c => c.chunk_key))
              const merged = [...prev]
              for (const chunk of streaming.retrievedChunks) {
                if (!seen.has(chunk.chunk_key)) {
                  seen.add(chunk.chunk_key)
                  merged.push(chunk)
                }
              }
              return merged
            })
          }

          // Reload from DB to get real IDs (deletable) and authoritative content.
          // Pass localAssistantMsg as fallback: if _save_turn failed on the backend
          // and the DB doesn't yet contain this message, we keep the local copy so
          // the assistant response remains visible.
          if (isCompletedConversationSelected) {
            loadMessages(localAssistantMsg)
          }
        } else {
          // No content — still reload to sync any state changes
          if (isCompletedConversationSelected) {
            loadMessages()
          }
        }

        scheduleConversationRefresh()

        if (
          isCompletedConversationSelected
          && !streaming.currentResponse
          && (!streaming.citations || streaming.citations.references.length === 0)
        ) {
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
    streaming.conversationId,
    selectedId,
    addLocal,
    loadMessages,
    scheduleConversationRefresh,
    messages.length,
    toast,
    t,
    createTempMessageId
  ])

  useEffect(() => {
    if (streaming.error) {
      toast.error(streaming.error)
    }
  }, [streaming.error, toast.error])

  const handleDeleteMessage = useCallback(async (msgId: number) => {
    if (msgId <= 0) {
      toast.warning(t('chat.message_not_persisted'))
      return
    }
    try {
      await removeMessage(msgId)
    } catch {
      toast.error(t('chat.delete_message_failed'))
    }
  }, [removeMessage, toast, t])

  const handleEditMessage = useCallback(async (msgId: number, newContent: string, editModelId: number | null, editKbIds: number[]) => {
    if (msgId <= 0) {
      toast.warning(t('chat.message_not_persisted'))
      return
    }
    const effectiveModelId = editModelId ?? modelId
    if (!selectedId || !effectiveModelId) return

    // Sync conversation settings if the user changed them in the edit dialog
    if (editModelId != null && editModelId !== modelId) {
      setModelId(editModelId)
      void update(selectedId, { model_id: editModelId }).catch((err) => {
        console.error('Failed to persist edited conversation model', err)
      })
    }
    const sortedEdit = [...editKbIds].sort().join(',')
    const sortedCurrent = [...kbIds].sort().join(',')
    if (sortedEdit !== sortedCurrent) {
      setKbIds(editKbIds)
      void update(selectedId, { kb_ids: editKbIds }).catch((err) => {
        console.error('Failed to persist edited conversation kb_ids', err)
      })
    }

    try {
      await editAndTruncate(msgId, newContent)
      // Re-send the edited message to get a new response
      const updatedMessages = messages.filter(m => {
        const target = messages.find(mm => mm.id === msgId)
        return target ? m.position <= target.position : true
      })
      // Replace the content of the edited message
      const allMsgs: ChatMessageType[] = []
      if (editKbIds.length > 0) {
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
      const options = editKbIds.length > 0
        ? { kb_ids: editKbIds, conversation_id: selectedId, citation_style: citationStyle, existing_references: [] }
        : undefined
      streaming.send(allMsgs, effectiveModelId, options, selectedId, streamOutputEnabled)
      if (editKbIds.length > 0) setPanelCollapsed(false)
    } catch {
      toast.error(t('chat.edit_failed'))
    }
  }, [selectedId, modelId, kbIds, messages, citationStyle, editAndTruncate, streaming, streamOutputEnabled, update, toast, t])

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
          formatted_citation: r.formatted_citation,
          chunk_index: r.chunk_index,
          chunk_content: r.chunk_content,
          knowledge_base_id: r.knowledge_base_id,
          score: r.score,
          chunks: r.chunks ?? []
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
      // Also clear summary so the manually entered title takes priority in the sidebar display
      await update(renamingConv.id, { title: name, summary: null })
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
    const allRefs = [
      ...(isStreamingForSelected ? (streaming.citations?.references ?? []) : []),
      ...messages
        .filter(m => m.role === 'assistant' && m.references)
        .flatMap(m => m.references ?? [])
    ]
    const targetRef = allRefs.find(r => r.ref_num === refNum)
    if (targetRef) {
      const targetChunk = targetRef.chunks && targetRef.chunks.length > 0
        ? targetRef.chunks[0]
        : {
            chunk_index: targetRef.chunk_index ?? refNum,
            chunk_content: targetRef.chunk_content || targetRef.formatted_citation,
          }
      setHighlightedChunkKey(`${targetRef.document_file_id}:${targetChunk.chunk_index}:${targetChunk.chunk_content}`)
    }
    setPanelCollapsed(false)
  }

  // Merge stored chunks from previous turns with live streaming chunks
  const displayChunks = (() => {
    if (!isStreamingForSelected && streaming.retrievedChunks.length === 0) return storedChunks
    // Merge: stored first, then new streaming chunks (dedup by chunk_index)
    const seen = new Set(storedChunks.map(c => c.chunk_key))
    const merged = [...storedChunks]
    for (const chunk of (isStreamingForSelected ? streaming.retrievedChunks : [])) {
      if (!seen.has(chunk.chunk_key)) {
        seen.add(chunk.chunk_key)
        merged.push(chunk)
      }
    }
    return merged
  })()

  const displayChunksWithMappedCiteNum = useMemo(
    () => displayChunks.map((chunk) => ({
      ...chunk,
      citation_num: globalLocalToDisplay.get(chunk.citation_num) ?? chunk.citation_num,
    })),
    [displayChunks, globalLocalToDisplay]
  )

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
              streamingContent={isStreamingForSelected ? streaming.currentResponse : undefined}
              isStreaming={isStreamingForSelected}
              isSearching={isStreamingForSelected && streaming.isSearching}
              searchQuery={isStreamingForSelected ? streaming.searchQuery : null}
              streamingReferences={isStreamingForSelected ? (streaming.citations?.references ?? null) : null}
              onCiteClick={handleCiteClick}
              onDeleteMessage={handleDeleteMessage}
              onEditMessage={handleEditMessage}
              onRegenerateMessage={handleRegenerateMessage}
              modelInfo={currentModelInfo}
              allModels={chatModels}
              allKbs={allKbs}
              currentModelId={modelId}
              currentKbIds={kbIds}
            />
            <div className="mt-auto">
              <ChatInput
                modelId={modelId}
                onModelChange={handleModelChange}
                kbIds={kbIds}
                onKBChange={setKbIds}
                onSend={handleSend}
                onAbort={streaming.abort}
                isStreaming={streaming.isStreaming}
              />
            </div>
          </div>
          {(kbIds.length > 0 || displayChunksWithMappedCiteNum.length > 0) && !panelCollapsed && (
            <ResizablePanel defaultWidth={340} minWidth={260} maxWidth={500} side="right" storageKey="chat_retrieval_panel_width">
              <RetrievalPanel
                chunks={displayChunksWithMappedCiteNum}
                collapsed={panelCollapsed}
                onToggle={() => setPanelCollapsed(!panelCollapsed)}
                highlightedChunkKey={highlightedChunkKey}
              />
            </ResizablePanel>
          )}
          {(kbIds.length > 0 || displayChunksWithMappedCiteNum.length > 0) && panelCollapsed && (
            <div className="shrink-0 bg-neutral-50/50 dark:bg-black/20">
              <RetrievalPanel
                chunks={displayChunksWithMappedCiteNum}
                collapsed={panelCollapsed}
                onToggle={() => setPanelCollapsed(!panelCollapsed)}
                highlightedChunkKey={highlightedChunkKey}
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
