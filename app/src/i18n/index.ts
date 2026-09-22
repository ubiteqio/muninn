import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

import de from '@/i18n/locales/de.json'

/**
 * German is the source language: every key is written here first, translations follow. All user
 * facing text goes through i18next, never straight into a component.
 */
export const defaultNS = 'translation'
export const resources = { de: { translation: de } } as const

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'de',
    supportedLngs: ['de'],
    defaultNS,
    interpolation: { escapeValue: false },
  })

export default i18n
