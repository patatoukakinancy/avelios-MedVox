import type { PublicCard } from '../protocol'

// A flat head-and-shoulders drawing, chosen by the patient's sex. Colours come from index.css.
export function PatientAvatar({ sex }: { sex: PublicCard['sex'] }) {
  const female = sex === 'female'

  return (
    <svg className="patient-avatar" viewBox="0 0 100 100" aria-hidden="true">
      {female && (
        <path className="hair" d="M50 15C34 15 27 27 28 43c.6 11-1 18-5 24 8 5 17 4 22 1h10c5 3 14 4 22-1-4-6-5.600-13-5-24 1-16-6-28-22-28Z" />
      )}
      <path className="clothes" d="M16 100c0-21 14-32 34-32s34 11 34 32Z" />
      <path className="skin" d={female ? 'M43 56h14v14c-3 6-11 6-14 0Z' : 'M43 56h14v13l-7 9-7-9Z'} />
      <ellipse className="skin" cx="50" cy="43" rx="16.5" ry="20" />
      <path
        className="hair"
        d={
          female
            ? 'M33 42c0-16 7-23 17-23s17 7 17 23c-8-1-16-6-19-13-3 7-8 12-15 13Z'
            : 'M33 42c-2-17 6-25 18-25 11 0 18 8 16 25-2-5-3-9-5-12-8 3-18 3-24-1-3 3-4 8-5 13Z'
        }
      />
      <g className="features">
        <circle cx="43.500" cy="45" r="1.8" />
        <circle cx="56.500" cy="45" r="1.8" />
        <path d="M44.500 54q5.500 3.500 11 0" />
      </g>
    </svg>
  )
}
