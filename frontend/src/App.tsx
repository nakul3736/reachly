import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import Feed from "./pages/Feed";
import JobDetailPage from "./pages/JobDetail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The index is refreshed daily by an external trigger, so refetching on every window
      // focus would spend requests to learn nothing.
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      // The API sleeps when idle on the free tier, and the first request after that can
      // fail while the container wakes. One retry turns a cold start into a slow load
      // rather than an error screen.
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function NotFound() {
  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pt-16 sm:px-6">
      <h1 className="font-display text-[32px] font-extrabold tracking-[-0.02em] text-ink">
        There is nothing at this address
      </h1>
      <p className="mt-3 text-[15px] text-slate">
        <a href="/" className="underline underline-offset-4">
          Go back to the feed
        </a>
      </p>
    </main>
  );
}
