import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./hooks/useAuth";
import { FeaturedPage } from "./pages/FeaturedPage";
import { RunListPage } from "./pages/RunListPage";
import { RunViewerPage } from "./pages/RunViewerPage";
import { NewRunPage } from "./pages/NewRunPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { UserProfilePage } from "./pages/UserProfilePage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<FeaturedPage />} />
          <Route path="/runs" element={<RunListPage />} />
          <Route path="/new" element={<NewRunPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/users/:userId" element={<UserProfilePage />} />
          <Route path="/runs/:runId" element={<RunViewerPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
