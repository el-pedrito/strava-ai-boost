import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import fr from './fr.json';

// French (the default, complete locale) is bundled eagerly so the first paint
// never waits or flashes. English is code-split and loaded on demand via
// setLanguage(), keeping ~50 KB of translation JSON out of the initial bundle.
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { fr: { translation: fr } },
    lng: 'fr',
    fallbackLng: 'fr',
    supportedLngs: ['fr', 'en'],
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
    partialBundledLanguages: true,
  });

async function ensureLanguage(lng: string): Promise<void> {
  const base = lng.split('-')[0];
  if (base === 'en' && !i18n.hasResourceBundle('en', 'translation')) {
    const en = (await import('./en.json')).default;
    i18n.addResourceBundle('en', 'translation', en, true, true);
  }
}

/**
 * Load the target locale's resources (if not already loaded) then switch to it.
 * Awaiting the resource load before changeLanguage() avoids a fallback flash.
 */
export async function setLanguage(lng: string): Promise<void> {
  await ensureLanguage(lng);
  await i18n.changeLanguage(lng);
}

export default i18n;
