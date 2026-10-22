import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { ThemeFollower } from "./components/ThemeToggle";
import { RunProvider } from "./RunContext";
import Dashboard from "./ui/Dashboard";
import Datasets from "./ui/Datasets";
import Groups from "./ui/Groups";
import Login from "./ui/Login";
import TestCases from "./ui/TestCases";
import VersionDetail from "./ui/VersionDetail";

export default function App() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-bg font-sans text-fg">
      <ThemeFollower />
      {user === undefined ? null : user === null ? (
        <Login />
      ) : (
        // the run tracker only starts once signed in (it calls protected endpoints)
        <RunProvider>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/v/:version" element={<VersionDetail />} />
            <Route path="/groups" element={<Groups />} />
            <Route path="/datasets" element={<Navigate to="/groups" replace />} />
            <Route path="/test-cases" element={<TestCases />} />
          </Routes>
        </RunProvider>
      )}
    </div>
  );
}
