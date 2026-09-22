import { PersonInitial } from '@/components/muninn/person-initial'

/** The signed-in user's own avatar, in header, sidebar and profile. */
export function OwnAvatar({
  name,
  size = 34,
  className,
}: {
  name: string
  size?: number
  className?: string
}) {
  return <PersonInitial name={name} size={size} className={className} />
}
