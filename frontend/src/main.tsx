import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tokens.css';
import './i18n';
import { loadConfig } from './config.ts';
import { ThemeProvider } from './theme/ThemeProvider.tsx';
import App from './App.tsx';

loadConfig().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </StrictMode>
  );
});
