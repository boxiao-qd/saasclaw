import { Routes, Route, Navigate } from "react-router-dom";
import { ChatLayout } from "@/components/page/ChatLayout";
import { NewChatPage } from "@/pages/NewChatPage";
import { ChatSessionPage } from "@/pages/ChatSessionPage";
import { SubagentsPage } from "@/pages/SubagentsPage";
import { SkillsPage } from "@/pages/SkillsPage";
import { NotificationPage } from "@/pages/NotificationPage";
import { CronPage } from "@/pages/CronPage";
import { FilesPage } from "@/pages/FilesPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { useAuthStore } from "@/store/auth-store";

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
            </ChatLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
