import { Route, Routes } from "react-router-dom";

function HomePage() {
  return <div>Home – Template Selection (placeholder)</div>;
}

function DashboardSelectPage() {
  return <div>Dashboard Select (placeholder)</div>;
}

function GeneratePage() {
  return <div>Generate (placeholder)</div>;
}

function AdminTemplatePage() {
  return <div>Admin – Template Management (placeholder)</div>;
}

function NotFound() {
  return <div>404 – Page not found</div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/dashboard-select" element={<DashboardSelectPage />} />
      <Route path="/generate" element={<GeneratePage />} />
      <Route path="/admin/template" element={<AdminTemplatePage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
