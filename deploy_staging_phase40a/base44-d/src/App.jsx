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
import VerifyEmailPage from './pages/VerifyEmailPage';

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
import SuperAdminPanel from './pages/SuperAdminPanel';
import AdminAccuracyCenter from './pages/AdminAccuracyCenter';
import AdminLearningDashboard from './pages/AdminLearningDashboard';
import AdminRoute from './components/AdminRoute';
import SuperAdminRoute from './components/SuperAdminRoute';
import PredictionHistoryPage from './pages/PredictionHistoryPage';
import FavoritesPage from './pages/FavoritesPage';
import AlertsPage from './pages/AlertsPage';
import ApiSettingsPage from './pages/ApiSettingsPage';
import PricingPage from './pages/PricingPage';

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
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      {/* Legal */}
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfService />} />
      <Route path="/disclaimer" element={<DisclaimerPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/imprint" element={<ImprintPage />} />

      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/matches" element={<MatchCenter />} />
          <Route path="/prediction/:id" element={<PredictionDetail />} />
          <Route path="/accuracy" element={<AccuracyCenter />} />
          <Route path="/subscription" element={<SubscriptionPage />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/history" element={<PredictionHistoryPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/api-settings" element={<AdminRoute><ApiSettingsPage /></AdminRoute>} />
          <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />
          <Route path="/super-admin" element={<SuperAdminRoute><SuperAdminPanel /></SuperAdminRoute>} />
          <Route path="/admin/accuracy" element={<AdminRoute><AdminAccuracyCenter /></AdminRoute>} />
          <Route path="/admin/learning" element={<AdminRoute><AdminLearningDashboard /></AdminRoute>} />
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