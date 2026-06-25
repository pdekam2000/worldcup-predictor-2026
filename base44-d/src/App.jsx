import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import ScrollToTop from './components/ScrollToTop';

// Auth pages
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';

// Public
import Landing from './pages/Landing';
import CookieConsent from './components/CookieConsent';

// Legal pages
import PrivacyPolicy from './pages/legal/PrivacyPolicy';
import TermsOfService from './pages/legal/TermsOfService';
import DisclaimerPage from './pages/legal/DisclaimerPage';
import ContactPage from './pages/legal/ContactPage';
import ImprintPage from './pages/legal/ImprintPage';

// Protected pages
import DashboardLayout from './components/dashboard/DashboardLayout';
import Dashboard from './pages/Dashboard';
import MatchCenter from './pages/MatchCenter';
import PredictionDetail from './pages/PredictionDetail';
import AccuracyCenter from './pages/AccuracyCenter';
import SubscriptionPage from './pages/SubscriptionPage';
import Notifications from './pages/Notifications';
import SettingsPage from './pages/SettingsPage';
import AdminPanel from './pages/AdminPanel';
import EliteShadowPreview from './pages/EliteShadowPreview';
import SuperAdminPanel from './pages/SuperAdminPanel';
import AdminRoute from './components/AdminRoute';
import SuperAdminRoute from './components/SuperAdminRoute';
import PredictionHistoryPage from './pages/PredictionHistoryPage';
import FavoritesPage from './pages/FavoritesPage';
import AlertsPage from './pages/AlertsPage';
import ApiSettingsPage from './pages/ApiSettingsPage';
import GoalTimingDashboardPage from './pages/goalTiming/GoalTimingDashboardPage';
import GoalTimingPicksPage from './pages/goalTiming/GoalTimingPicksPage';
import GoalTimingHistoryPage from './pages/goalTiming/GoalTimingHistoryPage';
import GoalTimingAccuracyPage from './pages/goalTiming/GoalTimingAccuracyPage';
import GoalTimingPerformancePage from './pages/goalTiming/GoalTimingPerformancePage';
import GoalTimingBacktestPage from './pages/goalTiming/GoalTimingBacktestPage';
import GoalTimingInsightsPage from './pages/goalTiming/GoalTimingInsightsPage';
import ResearchHighlights from './pages/ResearchHighlights';
import EliteWorldCupPage from './pages/EliteWorldCupPage';
import AdminPerformancePage from './pages/AdminPerformancePage';
import OwnerLogin from './pages/OwnerLogin';
import OwnerRoute from './components/OwnerRoute';
import OwnerDashboardGate from './components/OwnerDashboardGate';
import OwnerLayout from './components/owner/OwnerLayout';
import OwnerCommandCenter from './pages/owner/OwnerCommandCenter';
import OwnerAutonomousPage from './pages/owner/OwnerAutonomousPage';
import OwnerMonitoringPage from './pages/owner/OwnerMonitoringPage';
import OwnerNotificationsPage from './pages/owner/OwnerNotificationsPage';
import OwnerPerformancePage from './pages/owner/OwnerPerformancePage';
import OwnerModelCenter from './pages/owner/OwnerModelCenter';
import OwnerResearchLab from './pages/owner/OwnerResearchLab';
import OwnerHealthPage, { OwnerApiUsagePage, OwnerDatabasePage, OwnerLogsPage } from './pages/owner/OwnerHealthPage';

const AuthenticatedApp = () => {
  const { isLoadingAuth } = useAuth();

  if (isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/owner-login" element={<OwnerLogin />} />
      <Route path="/system/owner-access" element={<Navigate to="/owner-login" replace />} />

      {/* Legal */}
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfService />} />
      <Route path="/disclaimer" element={<DisclaimerPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/imprint" element={<ImprintPage />} />
      <Route path="/research/highlights" element={<ResearchHighlights />} />
      <Route path="/world-cup" element={<Navigate to="/matches?hub=worldcup" replace />} />
      <Route path="/account/settings" element={<Navigate to="/settings" replace />} />
      <Route path="/analytics/accuracy" element={<Navigate to="/accuracy" replace />} />
      <Route path="/admin/dashboard" element={<Navigate to="/admin" replace />} />

      <Route element={<OwnerRoute />}>
        <Route element={<OwnerLayout />}>
          <Route path="/owner" element={<OwnerCommandCenter />} />
          <Route path="/owner/autonomous" element={<OwnerAutonomousPage />} />
          <Route path="/owner/monitoring" element={<OwnerMonitoringPage />} />
          <Route path="/owner/notifications" element={<OwnerNotificationsPage />} />
          <Route path="/owner/performance" element={<OwnerPerformancePage />} />
          <Route path="/owner/model-center" element={<OwnerModelCenter />} />
          <Route path="/owner/research-lab" element={<OwnerResearchLab />} />
          <Route path="/owner/health" element={<OwnerHealthPage />} />
          <Route path="/owner/api-usage" element={<OwnerApiUsagePage />} />
          <Route path="/owner/database" element={<OwnerDatabasePage />} />
          <Route path="/owner/logs" element={<OwnerLogsPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>
        <Route element={<DashboardLayout />}>
          <Route element={<OwnerDashboardGate />}>
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>
          <Route path="/matches" element={<MatchCenter />} />
          <Route path="/prediction/:id" element={<PredictionDetail />} />
          <Route path="/goal-timing" element={<Navigate to="/goal-timing/dashboard" replace />} />
          <Route path="/goal-timing/dashboard" element={<GoalTimingDashboardPage />} />
          <Route path="/goal-timing/picks" element={<GoalTimingPicksPage />} />
          <Route path="/goal-timing/history" element={<GoalTimingHistoryPage />} />
          <Route path="/goal-timing/accuracy" element={<GoalTimingAccuracyPage />} />
          <Route path="/goal-timing/performance" element={<GoalTimingPerformancePage />} />
          <Route path="/goal-timing/backtest" element={<GoalTimingBacktestPage />} />
          <Route path="/goal-timing/insights" element={<GoalTimingInsightsPage />} />
          <Route path="/accuracy" element={<AccuracyCenter />} />
          <Route path="/subscription" element={<SubscriptionPage />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/history" element={<PredictionHistoryPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/api-settings" element={<ApiSettingsPage />} />
          <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />
          <Route path="/admin/elite-shadow" element={<SuperAdminRoute><EliteShadowPreview /></SuperAdminRoute>} />
          <Route path="/elite/world-cup" element={<SuperAdminRoute><EliteWorldCupPage /></SuperAdminRoute>} />
          <Route path="/admin/performance" element={<SuperAdminRoute><AdminPerformancePage /></SuperAdminRoute>} />
          <Route path="/super-admin" element={<SuperAdminRoute><SuperAdminPanel /></SuperAdminRoute>} />
        </Route>
      </Route>

      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};

function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <ScrollToTop />
          <AuthenticatedApp />
          <CookieConsent />
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App