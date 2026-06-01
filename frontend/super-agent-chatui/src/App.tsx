import { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ChatLayout } from "@/components/page/ChatLayout";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { useAuthStore } from "@/store/auth-store";

const NewChatPage = lazy(() => import("@/pages/NewChatPage").then((m) => ({ default: m.NewChatPage })));
const ChatSessionPage = lazy(() => import("@/pages/ChatSessionPage").then((m) => ({ default: m.ChatSessionPage })));
const SubagentsPage = lazy(() => import("@/pages/SubagentsPage").then((m) => ({ default: m.SubagentsPage })));
const SkillsPage = lazy(() => import("@/pages/SkillsPage").then((m) => ({ default: m.SkillsPage })));
const NotificationPage = lazy(() => import("@/pages/NotificationPage").then((m) => ({ default: m.NotificationPage })));
const CronPage = lazy(() => import("@/pages/CronPage").then((m) => ({ default: m.CronPage })));
const FilesPage = lazy(() => import("@/pages/FilesPage").then((m) => ({ default: m.FilesPage })));

function PageFallback() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] animate-pulse-cyan mx-auto" />
        <p className="text-[var(--color-text-tertiary)] font-mono text-xs mt-3">LOADING</p>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <ChatLayout>
              <Suspense fallback={<PageFallback />}>
                <Routes>
                  <Route path="/" element={<Navigate to="/chat/new" replace />} />
                  <Route path="/chat/new" element={<NewChatPage />} />
                  <Route path="/chat/:sessionId" element={<ChatSessionPage />} />
                  <Route path="/subagents" element={<SubagentsPage />} />
                  <Route path="/skills" element={<SkillsPage />} />
                  <Route path="/notifications" element={<NotificationPage />} />
                  <Route path="/cron" element={<CronPage />} />
                  <Route path="/files" element={<FilesPage />} />
                </Routes>
              </Suspense>
            </ChatLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
