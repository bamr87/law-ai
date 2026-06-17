import { Suspense } from 'react'
import LsatLab from '@/components/LsatLab'

export const metadata = {
  title: 'LSAT Lab · LawGraph AI',
  description:
    'Practice every LSAT section — Logical Reasoning, Reading Comprehension, Logic Games — with concept references and an open-source AI tutor.',
}

export default function LsatPage() {
  // LsatLab reads ?tab= via useSearchParams, which Next requires to sit under
  // a Suspense boundary.
  return (
    <Suspense>
      <LsatLab />
    </Suspense>
  )
}
