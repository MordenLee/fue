import { useState, useCallback } from 'react'
import { RotateCcw, Save, Languages, Database, FileText, Bot } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { FormField } from '../components/ui/FormField'
import { Select } from '../components/ui/Select'
import { Switch } from '../components/ui/Switch'
import { NumberInput } from '../components/ui/NumberInput'
import { ModelSelector } from '../components/shared/ModelSelector'
import { CitationStyleSelect } from '../components/shared/CitationStyleSelect'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { useSettings } from '../contexts/SettingsContext'
import { useToast } from '../contexts/ToastContext'
import { settingsService } from '../services/settings'
import type { SettingsUpdate } from '../types/settings'
import { useI18n } from '../i18n'

type SectionKey = 'general' | 'chat' | 'rag' | 'parsing' | 'models'

const sections: { key: SectionKey; icon: React.ElementType; labelKey: string }[] = [
  { key: 'general', icon: Languages, labelKey: 'settings_page.section_general' },
  { key: 'chat', icon: Bot, labelKey: 'settings_page.section_chat' },
  { key: 'rag', icon: Database, labelKey: 'settings_page.section_search' },
  { key: 'parsing', icon: FileText, labelKey: 'settings_page.section_parsing' },
  { key: 'models', icon: Bot, labelKey: 'settings_page.section_models' }
]

export function SettingsPage() {
  const { settings, reload, streamOutputEnabled, setStreamOutputEnabled } = useSettings()
  const toast = useToast()
  const { t } = useI18n()

  const [activeSection, setActiveSection] = useState<SectionKey>('general')
  const [form, setForm] = useState<SettingsUpdate>({})
  const [saving, setSaving] = useState(false)
  const [showReset, setShowReset] = useState(false)

  const current = { ...settings, ...form }

  const handleChange = useCallback((patch: Partial<SettingsUpdate>) => {
    setForm((prev) => ({ ...prev, ...patch }))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsService.update(form)
      await reload()
      setForm({})
      toast.success(t('settings.saved'))
    } catch {
      toast.error(t('common.save_failed'))
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    try {
      await settingsService.reset()
      await reload()
      setForm({})
      toast.success(t('settings.reset_done'))
    } catch {
      toast.error(t('settings_page.reset_failed'))
    }
    setShowReset(false)
  }

  if (!settings) return null

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-48 shrink-0 border-r border-black/8 dark:border-white/8 bg-neutral-50 dark:bg-neutral-900/50 flex flex-col py-3">
        {sections.map(({ key, icon: Icon, labelKey }) => (
          <button
            key={key}
            onClick={() => setActiveSection(key)}
            className={`flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-colors text-left
              ${activeSection === key
                ? 'bg-blue-50 dark:bg-blue-600/15 text-blue-600 dark:text-blue-400 font-medium'
                : 'text-neutral-600 dark:text-neutral-400 hover:bg-black/5 dark:hover:bg-white/5 hover:text-neutral-900 dark:hover:text-white'
              }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {t(labelKey)}
          </button>
        ))}

        <div className="mt-auto px-3 pt-3 border-t border-black/8 dark:border-white/8">
          <button
            onClick={() => setShowReset(true)}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs 
              text-neutral-500 dark:text-neutral-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t('settings_page.reset_defaults')}
          </button>
        </div>
      </aside>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-xl mx-auto px-8 py-8">

          {activeSection === 'general' && (
            <section>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-6">{t('settings_page.section_general')}</h2>
              <div className="space-y-5">
                <FormField label={t('settings.language_label')}>
                  <Select
                    value={current.language ?? 'zh'}
                    onValueChange={(v) => handleChange({ language: v as 'zh' | 'en' })}
                    options={[
                      { label: t('settings.language_zh'), value: 'zh' },
                      { label: t('settings.language_en'), value: 'en' }
                    ]}
                  />
                </FormField>
              </div>
            </section>
          )}

          {activeSection === 'chat' && (
            <section>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-6">{t('settings_page.section_chat')}</h2>
              <div className="space-y-5">
                <FormField label={t('settings_page.stream_output')} description={t('settings_page.stream_output_desc')}>
                  <Switch
                    checked={streamOutputEnabled}
                    onCheckedChange={setStreamOutputEnabled}
                  />
                </FormField>

                <FormField label={t('settings_page.chat_citation_mode')} description={t('settings_page.chat_citation_mode_desc')}>
                  <Select
                    value={current.chat_citation_mode ?? 'document'}
                    onValueChange={(v) => handleChange({ chat_citation_mode: v as 'document' | 'chunk' })}
                    options={[
                      { label: t('settings_page.chat_citation_mode_document'), value: 'document' },
                      { label: t('settings_page.chat_citation_mode_chunk'), value: 'chunk' }
                    ]}
                  />
                </FormField>

                <FormField label={t('settings_page.chat_citation_style')} description={t('settings_page.chat_citation_style_desc')}>
                  <CitationStyleSelect
                    value={current.chat_citation_style ?? 'apa'}
                    onChange={(v) => handleChange({ chat_citation_style: v as SettingsUpdate['chat_citation_style'] })}
                  />
                </FormField>

                <FormField label={t('settings_page.chat_history_turns')} description={t('settings_page.chat_history_turns_desc')}>
                  <NumberInput
                    className="w-28"
                    value={current.chat_history_turns ?? 5}
                    onChange={(v) => handleChange({ chat_history_turns: v })}
                    min={0}
                    max={50}
                  />
                </FormField>

                <FormField label={t('settings_page.chat_max_tool_rounds')} description={t('settings_page.chat_max_tool_rounds_desc')}>
                  <NumberInput
                    className="w-28"
                    value={current.chat_max_tool_rounds ?? 5}
                    onChange={(v) => handleChange({ chat_max_tool_rounds: v })}
                    min={1}
                    max={20}
                  />
                </FormField>

                <FormField label={t('settings_page.chat_compress_model')} description={t('settings_page.chat_compress_model_desc')}>
                  <ModelSelector
                    value={current.chat_compress_model_id ?? null}
                    onChange={(v) => handleChange({ chat_compress_model_id: v })}
                    modelType="chat"
                  />
                </FormField>
              </div>
            </section>
          )}

          {activeSection === 'rag' && (
            <section>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-6">{t('settings_page.section_search')}</h2>
              <div className="space-y-5">
                <FormField label={t('settings_page.single_search_top_k')} description={t('settings_page.single_search_top_k_desc')}>
                  <NumberInput className="w-28" value={current.rag_top_k ?? 5} onChange={(v) => handleChange({ rag_top_k: v })} min={1} max={50} />
                </FormField>
                <FormField label={t('settings_page.hybrid_keyword_floor_top_k')} description={t('settings_page.hybrid_keyword_floor_top_k_desc')}>
                  <NumberInput
                    className="w-28"
                    value={current.hybrid_keyword_floor_top_k ?? 10}
                    onChange={(v) => handleChange({ hybrid_keyword_floor_top_k: v })}
                    min={1}
                    max={100}
                  />
                </FormField>
              </div>
            </section>
          )}

          {activeSection === 'parsing' && (
            <section>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-6">{t('settings_page.section_parsing')}</h2>
              <div className="space-y-5">
                <FormField label={t('settings.pdf_parser')} description={t('settings_page.pdf_parser_desc')}>
                  <Select
                    value={current.pdf_parser ?? 'pdfplumber'}
                    onValueChange={(v) => handleChange({ pdf_parser: v as SettingsUpdate['pdf_parser'] })}
                    options={[
                      { label: 'pdfplumber', value: 'pdfplumber' },
                      { label: 'PyMuPDF', value: 'pymupdf' },
                      { label: 'PyPDF', value: 'pypdf' }
                    ]}
                  />
                </FormField>
                <FormField label={t('settings.docx_parser')} description={t('settings_page.docx_parser_desc')}>
                  <Select
                    value={current.docx_parser ?? 'python-docx'}
                    onValueChange={(v) => handleChange({ docx_parser: v as SettingsUpdate['docx_parser'] })}
                    options={[
                      { label: 'python-docx', value: 'python-docx' },
                      { label: 'MarkItDown', value: 'markitdown' }
                    ]}
                  />
                </FormField>
                <FormField label={t('settings.embed_max_concurrency')} description={t('settings_page.embed_max_concurrency_desc')}>
                  <NumberInput
                    className="w-28"
                    value={current.embed_max_concurrency ?? 4}
                    onChange={(v) => handleChange({ embed_max_concurrency: v })}
                    min={1}
                    max={32}
                    disabled={current.embed_use_model_qps ?? false}
                  />
                </FormField>
                <FormField label={t('settings.embed_use_model_qps')} description={t('settings_page.embed_use_model_qps_desc')}>
                  <Switch
                    checked={current.embed_use_model_qps ?? false}
                    onCheckedChange={(v) => handleChange({ embed_use_model_qps: v })}
                  />
                </FormField>
                <FormField label={t('settings.kb_index_max_workers')} description={t('settings_page.kb_index_max_workers_desc')}>
                  <NumberInput
                    className="w-28"
                    value={current.kb_index_max_workers ?? 4}
                    onChange={(v) => handleChange({ kb_index_max_workers: v })}
                    min={1}
                    max={16}
                  />
                </FormField>
              </div>
            </section>
          )}

          {activeSection === 'models' && (
            <section>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-6">{t('settings_page.section_models')}</h2>
              <div className="space-y-5">
                <FormField label={t('settings.doc_clean_model')} description={t('settings_page.doc_clean_model_desc')}>
                  <ModelSelector
                    value={current.doc_clean_model_id ?? null}
                    onChange={(v) => handleChange({ doc_clean_model_id: v })}
                    modelType="chat"
                  />
                </FormField>
                <FormField label={t('settings_page.doc_clean_keep_references')} description={t('settings_page.doc_clean_keep_references_desc')}>
                  <Switch
                    checked={current.doc_clean_keep_references ?? false}
                    onCheckedChange={(v) => handleChange({ doc_clean_keep_references: v })}
                  />
                </FormField>
                <FormField label={t('settings_page.doc_clean_keep_annotations')} description={t('settings_page.doc_clean_keep_annotations_desc')}>
                  <Switch
                    checked={current.doc_clean_keep_annotations ?? false}
                    onCheckedChange={(v) => handleChange({ doc_clean_keep_annotations: v })}
                  />
                </FormField>
                <FormField label={t('settings.chat_summary_model')} description={t('settings_page.chat_summary_model_desc')}>
                  <ModelSelector
                    value={current.chat_summary_model_id ?? null}
                    onChange={(v) => handleChange({ chat_summary_model_id: v })}
                    modelType="chat"
                  />
                </FormField>
                <FormField label={t('settings.info_extract_model')} description={t('settings_page.info_extract_model_desc')}>
                  <ModelSelector
                    value={current.info_extract_model_id ?? null}
                    onChange={(v) => handleChange({ info_extract_model_id: v })}
                    modelType="chat"
                  />
                </FormField>
              </div>
            </section>
          )}

          <div className="mt-8 flex justify-end">
            <Button onClick={handleSave} loading={saving} disabled={Object.keys(form).length === 0}>
              <Save className="h-4 w-4 mr-1" />
              {t('common.save')}
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={showReset}
        onOpenChange={() => setShowReset(false)}
        onConfirm={handleReset}
        title={t('settings_page.reset_dialog_title')}
        description={t('settings_page.reset_dialog_desc')}
        danger
      />
    </div>
  )
}
