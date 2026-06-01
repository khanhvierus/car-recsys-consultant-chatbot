import { Link } from "react-router-dom";
import { Heart, Fuel, Gauge, Settings2, Star } from "lucide-react";
import { useState } from "react";
import { Vehicle, formatPrice, trackVehicleClick, isAuthenticated } from "@/lib/api";
import { useAddFavorite, useRemoveFavorite, useFavorites } from "@/hooks/useApi";

interface VehicleCardProps {
  vehicle: Vehicle;
  onFavoriteToggle?: () => void;
}

export default function VehicleCard({ vehicle, onFavoriteToggle }: VehicleCardProps) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  
  const { data: favorites } = useFavorites();
  const addFavorite = useAddFavorite();
  const removeFavorite = useRemoveFavorite();
  
  const isFavorite = !!vehicle && (favorites?.some(f => f.vehicle_id === vehicle.vehicle_id) ?? false);

  if (!vehicle) return null;

  // Generate placeholder images
  const getPlaceholderImage = () => {
    const carImages = [
      'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=800&h=600&fit=crop&q=80',
      'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&h=600&fit=crop&q=80',
      'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&h=600&fit=crop&q=80',
      'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&h=600&fit=crop&q=80',
      'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800&h=600&fit=crop&q=80',
    ];
    
    // Use hash of vehicle_id for consistent placeholder
    const hash = vehicle.vehicle_id.split('').reduce((a, b) => a + b.charCodeAt(0), 0);
    return carImages[hash % carImages.length];
  };
  
  const imageUrl = imageError || !vehicle.image_url 
    ? getPlaceholderImage()
    : vehicle.image_url;

  const handleFavoriteClick = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!isAuthenticated()) {
      window.location.href = '/login';
      return;
    }

    try {
      if (isFavorite) {
        await removeFavorite.mutateAsync(vehicle.vehicle_id);
      } else {
        await addFavorite.mutateAsync(vehicle.vehicle_id);
      }
      onFavoriteToggle?.();
    } catch (error) {
      console.error('Failed to toggle favorite:', error);
    }
  };

  const handleClick = () => {
    trackVehicleClick(vehicle.vehicle_id);
  };

  return (
    <Link
      to={`/vehicle/${vehicle.vehicle_id}`}
      onClick={handleClick}
      className="group block bg-card rounded-lg overflow-hidden border border-border/30 hover:border-accent/30 transition-all duration-300 hover:shadow-lg"
    >
      {/* Image container */}
      <div className="relative aspect-[4/3] overflow-hidden bg-secondary">
        {!imageLoaded && (
          <div className="absolute inset-0 bg-secondary animate-pulse" />
        )}
        <img
          src={imageUrl}
          alt={vehicle.title || 'Vehicle'}
          className={`w-full h-full object-cover transition-all duration-500 group-hover:scale-105 ${
            imageLoaded ? "opacity-100" : "opacity-0"
          }`}
          onLoad={() => setImageLoaded(true)}
          onError={() => setImageError(true)}
        />
        
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-background/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
        
        {/* Condition badge */}
        {vehicle.condition && (
          <div className="absolute top-3 left-3 px-2.5 py-1 bg-background/90 backdrop-blur-sm rounded text-xs font-medium capitalize">
            {vehicle.condition}
          </div>
        )}
        
        {/* Rating badge */}
        {vehicle.car_rating && (
          <div className="absolute bottom-3 left-3 px-2.5 py-1 bg-accent/90 backdrop-blur-sm rounded text-xs font-medium text-accent-foreground flex items-center gap-1">
            <Star className="h-3 w-3 fill-current" />
            {vehicle.car_rating.toFixed(1)}
          </div>
        )}

        {/* Favorite button */}
        <button
          onClick={handleFavoriteClick}
          disabled={addFavorite.isPending || removeFavorite.isPending}
          className={`absolute top-3 right-3 w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
            isFavorite
              ? "bg-accent text-accent-foreground shadow-lg"
              : "bg-background/80 backdrop-blur-sm text-foreground hover:bg-background hover:scale-110"
          }`}
        >
          <Heart className={`h-4 w-4 transition-transform ${isFavorite ? "fill-current scale-110" : ""}`} />
        </button>
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Brand */}
        <p className="text-[11px] tracking-wider text-accent uppercase font-medium mb-1">
          {vehicle.brand || 'Unknown'}
        </p>
        
        {/* Title */}
        <h3 className="font-semibold text-lg text-foreground mb-1 line-clamp-1 group-hover:text-accent transition-colors">
          {vehicle.car_model || vehicle.title || 'Vehicle'}
        </h3>
        
        {/* Full title as subtitle */}
        <p className="text-sm text-muted-foreground mb-3 line-clamp-1">
          {vehicle.title}
        </p>

        {/* Price */}
        <p className="text-xl font-bold text-foreground mb-4">
          {formatPrice(vehicle.price)}
        </p>

        {/* Specs */}
        <div className="flex items-center gap-3 pt-3 border-t border-border/40">
          {vehicle.mileage_str && (
            <>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Gauge className="h-3.5 w-3.5 text-accent/70" />
                <span className="truncate">{vehicle.mileage_str}</span>
              </div>
              <div className="w-px h-3 bg-border/50" />
            </>
          )}
          
          {vehicle.fuel_type && (
            <>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Fuel className="h-3.5 w-3.5 text-accent/70" />
                <span className="truncate">{vehicle.fuel_type}</span>
              </div>
              <div className="w-px h-3 bg-border/50" />
            </>
          )}
          
          {vehicle.transmission && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Settings2 className="h-3.5 w-3.5 text-accent/70" />
              <span className="truncate">{vehicle.transmission.split(' ')[0]}</span>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
