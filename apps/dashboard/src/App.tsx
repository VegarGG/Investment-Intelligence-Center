import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Shell } from "./components/Shell";
import { AgentFeed } from "./routes/AgentFeed";
import { Chat } from "./routes/Chat";
import { Fundamental } from "./routes/Fundamental";
import { Health } from "./routes/Health";
import { Home } from "./routes/Home";
import { Intel } from "./routes/Intel";
import { Leaderboard } from "./routes/Leaderboard";
import { Personas } from "./routes/Personas";
import { Quant } from "./routes/Quant";
import { TradeTape } from "./routes/TradeTape";
import { WatchlistAdmin } from "./routes/admin/Watchlist";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/agents/:agent" element={<AgentFeed />} />
            <Route path="/tape" element={<TradeTape />} />
            <Route path="/intel" element={<Intel />} />
            <Route path="/quant" element={<Quant />} />
            <Route path="/fundamental" element={<Fundamental />} />
            <Route path="/personas" element={<Personas />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/health" element={<Health />} />
            <Route path="/admin/watchlist" element={<WatchlistAdmin />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
