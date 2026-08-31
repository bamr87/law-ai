import type { LsatRepresentation } from '@/lib/api'

import ArgumentMap from './ArgumentMap'
import GroupGrid from './GroupGrid'
import PassageMap from './PassageMap'
import RuleNotation from './RuleNotation'
import SequenceBoard from './SequenceBoard'

/**
 * Dispatcher over the typed representation union (spec 041 FR-2/FR-7).
 * The exhaustive switch fails to compile when a new `rep_type` is added
 * without a renderer.
 */
export default function Representation({ rep }: { rep: LsatRepresentation }) {
  switch (rep.rep_type) {
    case 'sequence':
      return <SequenceBoard rep={rep} />
    case 'grid':
      return <GroupGrid rep={rep} />
    case 'notation':
      return <RuleNotation rep={rep} />
    case 'argument_map':
      return <ArgumentMap rep={rep} />
    case 'passage_map':
      return <PassageMap rep={rep} />
    default: {
      const exhaustive: never = rep
      return exhaustive
    }
  }
}
