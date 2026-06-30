import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './query/queryClient';
import { App } from './App';
import { LoginGate } from './auth/LoginGate';

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <LoginGate>
      <App />
    </LoginGate>
  </QueryClientProvider>,
);
