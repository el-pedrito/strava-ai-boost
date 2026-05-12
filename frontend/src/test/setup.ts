import '@testing-library/jest-dom/vitest';
import '../i18n';
import i18n from '../i18n';

// Force English for predictable test assertions.
void i18n.changeLanguage('en');
