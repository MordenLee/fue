import anthropicLogo from '../assets/providers/anthropic.svg'
import deepseekLogo from '../assets/providers/deepseek.svg'
import googleLogo from '../assets/providers/google.svg'
import moonshotLogo from '../assets/providers/moonshot.svg'
import openaiLogo from '../assets/providers/openai.svg'
import siliconflowLogo from '../assets/providers/siliconflow.svg'
import zhipuLogo from '../assets/providers/zhipu.svg'

const providerLogoMap: Record<string, string> = {
  openai: openaiLogo,
  anthropic: anthropicLogo,
  deepseek: deepseekLogo,
  'moonshot ai': moonshotLogo,
  moonshot: moonshotLogo,
  '智谱 ai': zhipuLogo,
  '智谱ai': zhipuLogo,
  zhipu: zhipuLogo,
  google: googleLogo,
  siliconflow: siliconflowLogo
}

export function getProviderLogo(name: string): string | null {
  return providerLogoMap[name.toLowerCase()] ?? null
}
