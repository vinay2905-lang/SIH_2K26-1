import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Empty, Spinner } from "./components/ui";
import { Dashboard, Queue } from "./pages/Dashboard";
import { InstitutionApplication, MyApplications } from "./pages/Institution";
import Login from "./pages/Login";
import { AuditTrail, Report, VerificationLog } from "./pages/Records";
import Rulebook from "./pages/Rulebook";
import Workspace from "./pages/Workspace";

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <Empty><Spinner label="Loading…" /></Empty>;
  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  const home = user.role === "institution" ? "/my" : "/dashboard";
  return (
    <Layout>
      <Routes>
        {user.role === "institution" ? (
          <>
            <Route path="/my" element={<MyApplications />} />
            <Route path="/my/:id" element={<InstitutionApplication />} />
          </>
        ) : (
          <>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/applications/:id" element={<Workspace />} />
            <Route path="/applications/:id/report" element={<Report />} />
            <Route path="/verification" element={<VerificationLog />} />
            <Route path="/rulebook" element={<Rulebook />} />
            <Route path="/audit" element={<AuditTrail />} />
          </>
        )}
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Layout>
  );
}
