import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { ThemeProvider } from "next-themes";
import Index from "./pages/Index";
import SearchPage from "./pages/SearchPage";
import VehicleDetailPage from "./pages/VehicleDetailPage";
import ComparePage from "./pages/ComparePage";
import SellPage from "./pages/SellPage";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import NotFound from "./pages/NotFound";
import ChatPopup from "./components/ChatPopup";

const queryClient = new QueryClient();

const App = () => (
  <HelmetProvider>
    <ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light" enableSystem={false}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/vehicle/:id" element={<VehicleDetailPage />} />
              <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
              <Route path="/compare" element={<ComparePage />} />
              <Route path="/sell" element={<SellPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/chat" element={<ChatPage />} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
            <ChatPopup />
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </HelmetProvider>
);

export default App;
