import '@testing-library/jest-dom/vitest';
import { setLanguage } from '../i18n';

// Force English for predictable test assertions (loads the lazy en bundle first).
await setLanguage('en');
