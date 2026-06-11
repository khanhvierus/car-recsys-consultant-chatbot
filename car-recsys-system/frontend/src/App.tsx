import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { ThemeProvider } from "next-themes";
import { GoogleOAuthProvider } from "@react-oauth/google";
import Index from "./pages/Index";
import SearchPage from "./pages/SearchPage";
import VehicleDetailPage from "./pages/VehicleDetailPage";
import ComparePage from "./pages/ComparePage";
import SellPage from "./pages/SellPage";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import FavoritesPage from "./pages/FavoritesPage";
import ProfilePage from "./pages/ProfilePage";
import NotFound from "./pages/NotFound";
import ChatPopup from "./components/ChatPopup";
import ScrollToTop from "./components/ScrollToTop";
import ScrollUpButton from "./components/ScrollUpButton";

const queryClient = new QueryClient();
const googleClientId =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  "893613114700-5e57386c5b899286dc2cv2j3d571scah.apps.googleusercontent.com";

const App = () => (
  <GoogleOAuthProvider clientId={googleClientId}>
    <HelmetProvider>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <BrowserRouter>
              <ScrollToTop />
              <Routes>
                <Route path="/" element={<Index />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/vehicle/:id" element={<VehicleDetailPage />} />
                <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
                <Route path="/compare" element={<ComparePage />} />
                <Route path="/sell" element={<SellPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/favorites" element={<FavoritesPage />} />
                <Route path="/profile" element={<ProfilePage />} />
                {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                <Route path="*" element={<NotFound />} />
              </Routes>
              <ChatPopup />
              <ScrollUpButton />
            </BrowserRouter>
          </TooltipProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </HelmetProvider>
  </GoogleOAuthProvider>
);

export default App;