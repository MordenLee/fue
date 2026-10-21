import { useCallback, useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor, type Editor, type JSONContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { FileText, Bold, Italic, List, ListOrdered, Quote, Undo2, Redo2, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { FolderListSidebar } from '../components/shared/FolderListSidebar'
import { ResizablePanel } from '../components/ui/ResizablePanel'

type DocumentItem = { id: string; title: string; updatedAt: string }
type WritingDocument = DocumentItem & { content: JSONContent }

export function WritingPage(): React.JSX.Element {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [status, setStatus] = useState('')
  const [revision, setRevision] = useState(0)
  const [search, setSearch] = useState('')
  const [outlineVisible, setOutlineVisible] = useState(() => localStorage.getItem('writing_outline_visible') !== 'false')
  const active = useRef<WritingDocument | null>(null)
  const loadedEditor = useRef<Editor | null>(null)
  const content = useRef<JSONContent>({ type: 'doc', content: [{ type: 'paragraph' }] })
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dirty = useRef(false)
  const changeVersion = useRef(0)
  const save = useRef<() => Promise<boolean>>(async () => true)
  const editor = useEditor({
    extensions: [StarterKit, Placeholder.configure({ placeholder: '开始写作…' })],
    content: { type: 'doc', content: [{ type: 'paragraph' }] },
    editorProps: { attributes: { class: 'writing-editor outline-none' } },
    onUpdate: ({ editor: changedEditor }) => {
      if (loadedEditor.current !== changedEditor) return
      content.current = changedEditor.getJSON()
      setRevision((value) => value + 1)
      scheduleSave.current()
    },
    onSelectionUpdate: () => setRevision((value) => value + 1)
  })
  const scheduleSave = useRef<() => void>(() => {})

  useEffect(() => {
    localStorage.setItem('writing_outline_visible', String(outlineVisible))
  }, [outlineVisible])

  save.current = async () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    if (!active.current || !editor || !dirty.current) return true
    const snapshot = { id: active.current.id, title: active.current.title, content: content.current }
    const version = changeVersion.current
    setStatus('保存中…')
    try {
      const result = await window.api.writingSave(snapshot)
      dirty.current = changeVersion.current !== version
      setDocuments((items) => items.map((item) => item.id === snapshot.id
        ? { ...item, title: snapshot.title, updatedAt: result.updatedAt } : item))
      setStatus(dirty.current ? '未保存' : '已保存')
      if (dirty.current) scheduleSave.current()
      return true
    } catch (error) {
      setStatus(`保存失败：${error instanceof Error ? error.message : String(error)}`)
      return false
    }
  }
  scheduleSave.current = () => {
    if (!active.current) return
    dirty.current = true
    changeVersion.current += 1
    setStatus('未保存')
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { void save.current() }, 600)
  }

  const open = useCallback(async (id: string) => {
    if (!editor || id === active.current?.id) return
    if (!await save.current()) return
    try {
      const document = await window.api.writingRead(id) as WritingDocument
      active.current = document
      loadedEditor.current = editor
      content.current = document.content
      dirty.current = false
      setActiveId(document.id)
      setTitle(document.title)
      editor.commands.setContent(document.content, { emitUpdate: false })
      setRevision((value) => value + 1)
      setStatus('已保存')
    } catch (error) {
      setStatus(`打开失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }, [editor])

  useEffect(() => {
    if (!editor) return
    active.current = null
    loadedEditor.current = null
    dirty.current = false
    let cancelled = false
    void window.api.writingList().then((items) => {
      if (cancelled) return
      setDocuments(items)
      if (items[0]) void open(items[0].id)
    }).catch((error: Error) => setStatus(`加载失败：${error.message}`))
    return () => { cancelled = true }
  }, [editor, open])

  useEffect(() => {
    const onSave = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void save.current()
      }
    }
    const beforeUnload = (): void => {
      if (!dirty.current || !active.current) return
      const result = window.api.writingSaveSync({ id: active.current.id, title: active.current.title, content: content.current })
      if (result.error) console.error('Failed to save writing document before close:', result.error)
    }
    window.addEventListener('keydown', onSave)
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      window.removeEventListener('keydown', onSave)
      window.removeEventListener('beforeunload', beforeUnload)
      beforeUnload()
    }
  }, [editor])

  const create = async (): Promise<void> => {
    if (!editor) return
    if (!await save.current()) return
    try {
      const document = await window.api.writingCreate() as WritingDocument
      setDocuments((items) => [document, ...items])
      active.current = null
      await open(document.id)
      editor.commands.focus()
    } catch (error) {
      setStatus(`新建失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const headings: { level: number; text: string; position: number }[] = []
  void revision
  editor?.state.doc.descendants((node, position) => {
    if (node.type.name === 'heading') headings.push({ level: node.attrs.level as number, text: node.textContent, position })
  })

  return (
    <div className="flex h-full min-h-0 bg-white text-neutral-900 dark:bg-neutral-900 dark:text-neutral-100">
      <ResizablePanel defaultWidth={260} minWidth={200} maxWidth={400} storageKey="writing_sidebar_width" className="border-r border-neutral-200 dark:border-white/10">
        <FolderListSidebar
          title="文档"
          items={documents.filter((item) => item.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()))}
          folders={[]}
          selectedId={activeId}
          onSelect={(item) => { void open(item.id) }}
          onCreateNew={() => { void create() }}
          onSearch={setSearch}
          renderItem={(item) => <span className="flex min-w-0 items-center gap-2"><FileText size={15} className="shrink-0" /><span className="truncate">{item.title}</span></span>}
          createLabel="新建文档"
          searchPlaceholder="搜索文档..."
          getItemFolder={() => null}
          getContextMenuItems={(item) => [{ label: '打开', onClick: () => { void open(item.id) } }]}
          getFolderContextMenuItems={() => []}
          draggable={false}
        />
      </ResizablePanel>
      <section className="flex min-w-0 flex-1 flex-col">
        {activeId && editor ? <>
          <div className="flex shrink-0 items-center gap-2 border-b border-neutral-200 px-4 py-2 dark:border-white/10">
            <input value={title} onChange={(event) => {
              const next = event.target.value
              setTitle(next)
              if (active.current) active.current.title = next
              scheduleSave.current()
            }} className="min-w-0 flex-1 bg-transparent text-sm font-semibold outline-none" aria-label="文档标题" />
            <span className="text-xs text-neutral-500">{status}</span>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-neutral-200 px-4 py-2 dark:border-white/10">
            <Tool label={outlineVisible ? '隐藏大纲' : '显示大纲'} onClick={() => setOutlineVisible((visible) => !visible)}>
              {outlineVisible ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
            </Tool>
            <span className="mx-1 h-5 w-px bg-neutral-200 dark:bg-white/10" />
            <Tool label="正文" active={editor.isActive('paragraph')} onClick={() => editor.chain().focus().setParagraph().run()} />
            {[1, 2, 3].map((level) => <Tool key={level} label={`H${level}`} active={editor.isActive('heading', { level })} onClick={() => editor.chain().focus().toggleHeading({ level: level as 1 | 2 | 3 }).run()} />)}
            <span className="mx-1 h-5 w-px bg-neutral-200 dark:bg-white/10" />
            <Tool label="粗体" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}><Bold size={16} /></Tool>
            <Tool label="斜体" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}><Italic size={16} /></Tool>
            <Tool label="无序列表" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}><List size={16} /></Tool>
            <Tool label="有序列表" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}><ListOrdered size={16} /></Tool>
            <Tool label="引用" active={editor.isActive('blockquote')} onClick={() => editor.chain().focus().toggleBlockquote().run()}><Quote size={16} /></Tool>
            <span className="mx-1 h-5 w-px bg-neutral-200 dark:bg-white/10" />
            <Tool label="撤销" onClick={() => editor.chain().focus().undo().run()}><Undo2 size={16} /></Tool>
            <Tool label="重做" onClick={() => editor.chain().focus().redo().run()}><Redo2 size={16} /></Tool>
          </div>
          <div className="flex min-h-0 flex-1">
            {outlineVisible && <ResizablePanel defaultWidth={190} minWidth={140} maxWidth={320} storageKey="writing_outline_width" className="border-r border-neutral-200 dark:border-white/10" resizeHandleClassName="!w-2 bg-neutral-200/50 dark:bg-white/10">
              <aside className="h-full w-full overflow-y-auto bg-neutral-50 px-3 py-4 dark:bg-neutral-900/50">
                <strong className="text-xs text-neutral-500">大纲</strong>
                <div className="mt-3 space-y-1">{headings.map((heading) => <button key={heading.position} onClick={() => {
                  editor.chain().focus().setTextSelection(heading.position + 1).run()
                  editor.commands.scrollIntoView()
                }} className="block w-full truncate rounded px-2 py-1 text-left text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800" style={{ paddingLeft: 8 + (heading.level - 1) * 12 }}>{heading.text || '未命名标题'}</button>)}</div>
              </aside>
            </ResizablePanel>}
            <div className="min-w-0 flex-1 overflow-y-auto bg-white dark:bg-neutral-900">
              <div className="min-h-full px-10 py-8"><EditorContent editor={editor} /></div>
            </div>
          </div>
        </> : <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">新建文档，开始写作</div>}
      </section>
    </div>
  )
}

function Tool({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children?: React.ReactNode }): React.JSX.Element {
  return <button type="button" title={label} aria-label={label} onClick={onClick}
    className={`min-w-8 rounded px-2 py-1.5 text-xs ${active ? 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200' : 'hover:bg-neutral-100 dark:hover:bg-neutral-800'}`}>{children || label}</button>
}
