import NiceModal from '@ebay/nice-modal-react';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from '@/routes';
import { ToastContainer } from '@/components/common';
import { queryClient } from '@/lib/queryClient';
import { ThemeProvider } from '@/components/theme/ThemeProvider';

function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <NiceModal.Provider>
          <RouterProvider router={router} />
          <ToastContainer />
        </NiceModal.Provider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
