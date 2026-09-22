import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * tailwind-merge only knows Tailwind's own sizes. Ours ("xs-plus", "3xs", "title" …) it took for
 * colours, and dropped them as soon as a colour stood beside them: "text-xs-plus
 * text-muted-foreground" came out as the colour alone, in the default size.
 */
const merge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        {
          text: ['2xs', '3xs', 'xs-plus', 'sm-plus', 'base-plus', 'title', 'title-lg'],
        },
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs))
}
