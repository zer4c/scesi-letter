import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider } from './modules/auth/AuthProvider.jsx';
import InvitationPage from './modules/auth/InvitationPage.jsx';
import LoginPage from './modules/auth/LoginPage.jsx';
import OrganizationAccessPage from './modules/auth/OrganizationAccessPage.jsx';
import { AdminRoute, ProtectedRoute } from './modules/auth/ProtectedRoute.jsx';
import ApplicationShell from './modules/layout/ApplicationShell.jsx';
import DocumentListPage from './modules/document/DocumentListPage.jsx';
import SignatureSettingsPage from './modules/signature/SignatureSettingsPage.jsx';

const DocumentEditorPage = lazy(() => import('./modules/document/DocumentEditorPage.jsx'));

function NotFoundPage() {
  return (
    <main className="not-found">
      <h1>Esta página no está disponible</h1>
      <a href="/documents">Volver a cartas</a>
    </main>
  );
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite/:token" element={<InvitationPage />} />
        <Route path="/invite" element={<InvitationPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<ApplicationShell />}>
            <Route index element={<Navigate to="/documents" replace />} />
            <Route path="/documents" element={<DocumentListPage />} />
            <Route path="/documents/:documentId" element={<Suspense fallback={<p className="screen-status" role="status">Preparando el editor…</p>}><DocumentEditorPage /></Suspense>} />
            <Route path="/settings/signature" element={<SignatureSettingsPage />} />
            <Route element={<AdminRoute />}>
              <Route path="/settings/organization" element={<OrganizationAccessPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
