import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import AgentApp from './App';
import './styles.css';

const container = document.getElementById('root');
if (container) {
  createRoot(container).render(
    <StrictMode>
      <AgentApp />
    </StrictMode>,
  );
}
