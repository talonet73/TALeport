import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, jsonBody } from './client'
import type { Language } from './types'

export type SourceKind = 'wikipedia' | 'reddit' | 'youtube' | 'video' | 'document' | 'text' | 'web'
export type SourceStatus = 'found' | 'queued' | 'processing' | 'ready' | 'error'

export interface DigestPoint {
  kind: string
  text: string
  time: string
}

export interface ResearchSource {
  id: number
  project_id: number
  kind: SourceKind
  title: string
  url: string
  author: string
  language: string | null
  status: SourceStatus
  step: 'runtime' | 'download' | 'transcribe' | 'summary' | null
  error_code: string | null
  meta: { duration?: number; views?: number | null; site?: string }
  chars: number
  digest: { summary: string; points: DigestPoint[] } | null
  created_at: string
  content?: string
}

export interface ResearchPlan {
  title: string
  questions: string[]
  keywords: Record<string, string[]>
  wikipedia: Record<string, string[]>
  reddit_queries: string[]
  youtube_queries: string[]
  content_types: string[]
}

export interface DossierItem {
  text: string
  sources: number[]
}

export const DOSSIER_SECTIONS = ['notions', 'rules', 'examples', 'experiences', 'mistakes', 'quotes'] as const
export type DossierSection = (typeof DOSSIER_SECTIONS)[number]

export type Dossier = Record<DossierSection, DossierItem[]> & {
  title: string
  summary: string
  ai_knowledge: DossierItem[]
  gaps: string[]
  sources: { n: number; id: number; title: string; url: string; kind: SourceKind }[]
}

export interface Article {
  title: string
  subtitle: string
  intro: string
  sections: { heading: string; paragraphs: string[] }[]
  conclusion: string
  sources_used: number[]
  language: Language
}

export interface ResearchProject {
  id: number
  goal: string
  title: string
  languages: Language[]
  plan: ResearchPlan | null
  dossier: Dossier | null
  article: Article | null
  collecting: boolean
  sources: ResearchSource[]
  created_at: string
  updated_at: string
}

export interface ResearchSummary {
  id: number
  goal: string
  title: string
  updated_at: string
  has_dossier: boolean
  sources: number
}

export const researchKey = (id: number) => ['research', id] as const

export function useResearchList() {
  return useQuery({ queryKey: ['research'], queryFn: () => api<ResearchSummary[]>('/research') })
}

export function useResearch(id: number | null) {
  return useQuery({
    queryKey: researchKey(id ?? 0),
    queryFn: () => api<ResearchProject>(`/research/${id}`),
    enabled: id !== null,
  })
}

/** Any research call that answers with the updated project: the cache is refreshed. */
export function useResearchAction<V>(id: number, call: (vars: V) => Promise<ResearchProject>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (project) => {
      queryClient.setQueryData(researchKey(id), project)
      void queryClient.invalidateQueries({ queryKey: ['research'], exact: true })
    },
  })
}

export const researchApi = {
  create: (goal: string, languages: Language[]) =>
    api<ResearchProject>('/research', { method: 'POST', body: jsonBody({ goal, languages }) }),
  update: (id: number, changes: Partial<Pick<ResearchProject, 'goal' | 'title' | 'languages' | 'plan' | 'dossier'>>) =>
    api<ResearchProject>(`/research/${id}`, { method: 'PATCH', body: jsonBody(changes) }),
  remove: (id: number) => api<void>(`/research/${id}`, { method: 'DELETE' }),
  collect: (id: number) => api<ResearchProject>(`/research/${id}/collect`, { method: 'POST' }),
  addVideos: (id: number, urls: string[]) =>
    api<ResearchProject>(`/research/${id}/videos`, { method: 'POST', body: jsonBody({ urls }) }),
  addDocument: (id: number, filename: string, data_base64: string) =>
    api<ResearchProject>(`/research/${id}/documents`, { method: 'POST', body: jsonBody({ filename, data_base64 }) }),
  addText: (id: number, title: string, text: string) =>
    api<ResearchProject>(`/research/${id}/texts`, { method: 'POST', body: jsonBody({ title, text }) }),
  source: (sourceId: number) => api<ResearchSource>(`/research/sources/${sourceId}`),
  deleteSource: (sourceId: number) => api<ResearchProject>(`/research/sources/${sourceId}`, { method: 'DELETE' }),
  transcribe: (sourceId: number) =>
    api<ResearchProject>(`/research/sources/${sourceId}/transcribe`, { method: 'POST' }),
  retry: (sourceId: number) => api<ResearchProject>(`/research/sources/${sourceId}/retry`, { method: 'POST' }),
  dossierText: (id: number) => api<{ title: string; text: string }>(`/research/${id}/dossier/text`),
  articleDocx: (id: number) =>
    api<{ name: string; path: string }>(`/research/${id}/article/docx`, { method: 'POST' }),
}

export function articleAsMarkdown(article: Article, dossier: Dossier | null): string {
  const used = new Set(article.sources_used)
  const sources = (dossier?.sources ?? []).filter((s) => used.size === 0 || used.has(s.n))
  return [
    `# ${article.title}`,
    article.subtitle && `*${article.subtitle}*`,
    article.intro,
    ...article.sections.map((s) => [s.heading && `## ${s.heading}`, ...s.paragraphs].filter(Boolean).join('\n\n')),
    article.conclusion,
    sources.length ? sources.map((s) => `- ${s.title}${s.url ? ` — ${s.url}` : ''}`).join('\n') : '',
  ]
    .filter(Boolean)
    .join('\n\n')
}
