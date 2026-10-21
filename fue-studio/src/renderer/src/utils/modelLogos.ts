import claudeLogo from '../assets/models/claude.svg'
import deepseekLogo from '../assets/models/deepseek.svg'
import doubaoLogo from '../assets/models/doubao.svg'
import geminiLogo from '../assets/models/gemini.svg'
import kimiLogo from '../assets/models/kimi.svg'
import moonshotLogo from '../assets/models/moonshot.svg'
import openaiLogo from '../assets/models/openai.svg'
import qwenLogo from '../assets/models/qwen.svg'
import zhipuLogo from '../assets/models/zhipu.svg'

const modelLogos: { keyword: string; logo: string }[] = [
  { keyword: 'claude', logo: claudeLogo },
  { keyword: 'deepseek', logo: deepseekLogo },
  { keyword: 'doubao', logo: doubaoLogo },
  { keyword: 'gemini', logo: geminiLogo },
  { keyword: 'kimi', logo: kimiLogo },
  { keyword: 'moonshot', logo: moonshotLogo },
  { keyword: 'gpt', logo: openaiLogo },
  { keyword: 'o1', logo: openaiLogo },
  { keyword: 'o3', logo: openaiLogo },
  { keyword: 'o4', logo: openaiLogo },
  { keyword: 'openai', logo: openaiLogo },
  { keyword: 'qwen', logo: qwenLogo },
  { keyword: 'glm', logo: zhipuLogo },
  { keyword: 'zhipu', logo: zhipuLogo },
]

export function getModelLogo(name: string): string | null {
  const lower = name.toLowerCase()
  for (const { keyword, logo } of modelLogos) {
    if (lower.includes(keyword)) return logo
  }
  return null
}
