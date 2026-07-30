import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import PapersPage from './pages/PapersPage';
import DomainPage from './pages/DomainPage';
import SearchPage from './pages/SearchPage';
import PaperDetailPage from './pages/PaperDetailPage';
import EditorialPage from './pages/EditorialPage';
import Layout from './components/Layout';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/papers" element={<PapersPage />} />
            <Route path="/domain/:slug" element={<DomainPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/paper/:id" element={<PaperDetailPage />} />
            <Route path="/editorial" element={<EditorialPage />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
