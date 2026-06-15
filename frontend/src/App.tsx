import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import AdminTemplatePage from "./pages/AdminTemplatePage";
import GenieSpaceSelectPage from "./pages/GenieSpaceSelectPage";
import { EditPage } from "./pages/EditPage";
import GeneratePage from "./pages/GeneratePage";
import HomePage from "./pages/HomePage";

function NotFound() {
  const location = useLocation();
  return (
    <div className="app">
      <header className="app-header">
        <div>
          <span className="eyebrow">Error</span>
          <h1>Page not found</h1>
        </div>
      </header>
      <main className="app-main">
        <div className="empty-state empty-state--rich">
          <div className="empty-state__mark" aria-hidden />
          <p className="empty-state__lede">
            The page you{'’'}re looking for doesn{'’'}t exist or has moved.
          </p>
          <p className="empty-state__detail mono">Requested path: {location.pathname}</p>
          <div className="empty-state__actions">
            <NavLink to="/" end className="btn btn--primary">
              Go home
            </NavLink>
            <NavLink to="/admin/template" className="btn btn--ghost">
              Register a new template
            </NavLink>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/space-select" element={<GenieSpaceSelectPage />} />
        <Route path="/generate" element={<GeneratePage />} />
        <Route path="/decks/:deckId/edit" element={<EditPage />} />
        <Route path="/admin/template" element={<AdminTemplatePage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
