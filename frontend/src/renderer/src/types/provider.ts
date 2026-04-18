export type InterfaceType = 'openai' | 'anthropic' | 'google' | 'ollama' | 'openai_compatible' | 'cohere' | 'jina'
export type ModelType = 'chat' | 'embedding' | 'reranking'
export type Capability = 'vision' | 'reasoning' | 'function_calling'

export interface ProviderOut {
  id: number
  name: string
  interface_type: InterfaceType
  api_base_url: string | null
  api_key: string | null
  description: string | null
  is_enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface ProviderCreate {
  name: string
  interface_type: InterfaceType
  api_base_url?: string | null
  api_key?: string | null
  description?: string | null
  is_enabled?: boolean
}

export interface ProviderUpdate {
  name?: string
  interface_type?: InterfaceType
  api_base_url?: string | null
  api_key?: string | null
  description?: string | null
  is_enabled?: boolean
}

export interface ProviderTestResult {
  success: boolean
  message: string
  latency_ms: number
}

export interface AIModelOut {
  id: number
  provider_id: number
  provider_name: string
  api_name: string
  display_name: string
  series: string | null
  model_type: ModelType
  capabilities: Capability[] | null
  context_length: number | null
  is_enabled: boolean
  is_default: boolean
  temperature: number | null
  top_p: number | null
  qps: number | null
  created_at: string
  updated_at: string
}

export interface AIModelCreate {
  provider_id: number
  api_name: string
  display_name: string
  series?: string | null
  model_type: ModelType
  capabilities?: Capability[] | null
  context_length?: number | null
  is_enabled?: boolean
  temperature?: number | null
  top_p?: number | null
  qps?: number | null
}

export interface AIModelUpdate {
  api_name?: string
  display_name?: string
  series?: string | null
  model_type?: ModelType
  capabilities?: Capability[] | null
  context_length?: number | null
  is_enabled?: boolean
  is_default?: boolean
  temperature?: number | null
  top_p?: number | null
  qps?: number | null
}

export interface DefaultModels {
  chat: AIModelOut | null
  embedding: AIModelOut | null
  reranking: AIModelOut | null
}
