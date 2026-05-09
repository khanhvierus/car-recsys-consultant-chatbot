import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import VehicleCard from "@/components/VehicleCard";
import { useFavorites } from "@/hooks/useApi";
import { isAuthenticated, getCurrentUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Loader2, Heart, ArrowLeft } from "lucide-react";

export default function FavoritesPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<{ username: string } | null>(null);
  const { data: favorites, isLoading, error, refetch } = useFavorites();
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    // Check authentication on mount
    if (!isAuthenticated()) {
      // Redirect to login if not authenticated
      navigate('/login');
      return;
    }
    
    const currentUser = getCurrentUser();
    setUser(currentUser);
  }, [navigate]);

  const handleFavoriteToggle = () => {
    // Force refresh after favorite toggle
    setRefreshKey((prev) => prev + 1);
    refetch();
  };

  return (
    <>
      <Helmet>
        <title>My Favorites - Car Recommendation System</title>
        <meta name="description" content="View and manage your favorite vehicles" />
      </Helmet>

      <div className="min-h-screen bg-background">
        <Header />
        
        <main className="container mx-auto px-4 py-8 mt-20">
          {/* Header Section */}
          <div className="mb-8">
            <Link to="/">
              <Button variant="ghost" className="mb-4">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Home
              </Button>
            </Link>
            
            <div className="flex items-center gap-3 mb-2">
              <Heart className="h-8 w-8 text-red-500 fill-red-500" />
              <h1 className="text-4xl font-bold">My Favorites</h1>
            </div>
            
            {user && (
              <p className="text-muted-foreground">
                Viewing favorites for <span className="font-semibold">{user.username}</span>
              </p>
            )}
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex justify-center items-center min-h-[400px]">
              <div className="text-center">
                <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-primary" />
                <p className="text-muted-foreground">Loading your favorites...</p>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="bg-destructive/10 border border-destructive rounded-lg p-6 mb-4">
                  <p className="text-destructive font-semibold mb-2">Failed to load favorites</p>
                  <p className="text-sm text-muted-foreground">
                    {error instanceof Error ? error.message : "An error occurred"}
                  </p>
                </div>
                <Button onClick={() => refetch()}>
                  Try Again
                </Button>
              </div>
            </div>
          )}

          {/* Not Logged In */}
          {!user && !isLoading && (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <Heart className="h-24 w-24 mx-auto mb-6 text-muted-foreground/30" />
                <h2 className="text-2xl font-semibold mb-4">Login Required</h2>
                <p className="text-muted-foreground mb-6">
                  Please log in to view and manage your favorite vehicles.
                </p>
                <Link to="/login">
                  <Button size="lg">
                    Go to Login
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {/* Empty State */}
          {user && !isLoading && !error && (!favorites || favorites.length === 0) && (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <Heart className="h-24 w-24 mx-auto mb-6 text-muted-foreground/30" />
                <h2 className="text-2xl font-semibold mb-4">No Favorites Yet</h2>
                <p className="text-muted-foreground mb-6">
                  Start exploring vehicles and save your favorites by clicking the heart icon.
                </p>
                <Link to="/search">
                  <Button size="lg">
                    Browse Vehicles
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {/* Favorites Grid */}
          {user && !isLoading && favorites && favorites.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-6">
                {favorites.length} {favorites.length === 1 ? "vehicle" : "vehicles"} saved
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {favorites.map((favorite) => (
                  <VehicleCard
                    key={`${favorite.vehicle_id}-${refreshKey}`}
                    vehicle={favorite.vehicle as any}
                    onFavoriteToggle={handleFavoriteToggle}
                  />
                ))}
              </div>
            </div>
          )}
        </main>

        <Footer />
      </div>
    </>
  );
}
