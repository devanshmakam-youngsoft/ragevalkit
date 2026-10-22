/**
 * Legacy Datasets page — now redirected to /groups via App.tsx.
 * Kept as a stub that compiles cleanly with the new Group type.
 */
import { Navigate } from "react-router-dom";

export default function Datasets() {
  return <Navigate to="/test-cases/groups" replace />;
}
