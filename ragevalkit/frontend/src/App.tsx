import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { ServerErrorToast } from "./components/ServerErrorToast";
import { ThemeFollower } from "./components/ThemeToggle";
import { RunProvider } from "./context/RunContext";
import Dashboard from "./pages/Dashboard";
import Datasets from "./pages/Datasets";
import Groups from "./pages/Groups";
import Help from "./pages/Help";
import Login from "./pages/Login";
import TestCases from "./pages/TestCases";
import VersionDetail from "./pages/VersionDetail";

export default function App() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-bg font-sans text-fg">
      <ThemeFollower />
      <ServerErrorToast />
      {user === undefined ? null : user === null ? (
        <Login />
      ) : (
        // the run tracker only starts once signed in (it calls protected endpoints)
        <RunProvider>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/v/:version" element={<VersionDetail />} />
            <Route path="/test-cases" element={<TestCases />} />
            <Route path="/test-cases/groups" element={<Groups />} />
            <Route path="/test-cases/groups/:groupId" element={<TestCases />} />
            <Route path="/help" element={<Help />} />
            <Route path="/help/:guideId" element={<Help />} />
            {/* older links */}
            <Route path="/groups" element={<Navigate to="/test-cases/groups" replace />} />
            <Route path="/datasets" element={<Navigate to="/test-cases/groups" replace />} />
          </Routes>
        </RunProvider>
      )}
    </div>
  );
}
