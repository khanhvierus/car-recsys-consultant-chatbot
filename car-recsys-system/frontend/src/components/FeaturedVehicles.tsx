// import { ArrowRight, Loader2 } from "lucide-react";
// import { Link } from "react-router-dom";
// import VehicleCard from "./VehicleCard";
// import { Button } from "@/components/ui/button";
// import { usePopularVehicles } from "@/hooks/useApi";

// const FeaturedVehicles = () => {
//   const { data, isLoading, error } = usePopularVehicles(8);
  
//   const featuredVehicles = data?.recommendations?.slice(0, 4) || [];

//   return (
//     <section className="py-24 bg-background relative overflow-hidden">
//       {/* Subtle background decoration */}
//       <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-3xl h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />
//       <div className="absolute top-1/2 -right-64 w-80 h-80 bg-accent/3 rounded-full blur-3xl" />

//       <div className="container mx-auto px-4 relative">
//         {/* Section Header */}
//         <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 mb-14">
//           <div className="max-w-xl">
//             <span className="text-[10px] tracking-[0.2em] text-accent uppercase mb-4 block">
//               Hand-picked selection
//             </span>
//             <h2 className="font-heading text-3xl md:text-4xl lg:text-5xl font-medium text-foreground mb-4 tracking-tight">
//               Featured Vehicles
//             </h2>
//             <p className="text-muted-foreground">
//               Discover our most exclusive listings, carefully selected for
//               quality and value.
//             </p>
//           </div>

//           <Link to="/search">
//             <Button
//               variant="outline"
//               className="group tracking-wide px-6 h-12 rounded-sm border-border/50 hover:border-accent/50 hover:bg-accent/5 transition-all duration-500"
//             >
//               View All Inventory
//               <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
//             </Button>
//           </Link>
//         </div>

//         {/* Loading State */}
//         {isLoading && (
//           <div className="flex justify-center items-center py-20">
//             <Loader2 className="h-8 w-8 animate-spin text-accent" />
//             <span className="ml-3 text-muted-foreground">Loading featured vehicles...</span>
//           </div>
//         )}

//         {/* Error State */}
//         {error && !isLoading && (
//           <div className="text-center py-20">
//             <p className="text-muted-foreground">Unable to load vehicles. Please try again later.</p>
//           </div>
//         )}

//         {/* Vehicle Grid */}
//         {!isLoading && !error && featuredVehicles.length > 0 && (
//           <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
//             {featuredVehicles.map((item, index) => (
//               <div
//                 key={item.vehicle.vehicle_id}
//                 className="animate-fade-in opacity-0"
//                 style={{ animationDelay: `${0.1 + index * 0.1}s`, animationFillMode: 'forwards' }}
//               >
//                 <VehicleCard vehicle={item.vehicle} />
//               </div>
//             ))}
//           </div>
//         )}

//         {/* Empty State */}
//         {!isLoading && !error && featuredVehicles.length === 0 && (
//           <div className="text-center py-20">
//             <p className="text-muted-foreground">No featured vehicles available at the moment.</p>
//           </div>
//         )}

//         {/* Bottom CTA */}
//         <div className="mt-20 text-center">
//           <p className="text-muted-foreground mb-8">
//             Looking for something specific? We can help you find it.
//           </p>
//           <Link to="/search">
//             <Button
//               size="lg"
//               className="bg-accent hover:bg-champagne-dark text-accent-foreground font-body tracking-wide px-8 h-14 rounded-sm shadow-soft hover:shadow-elegant transition-all duration-500"
//             >
//               Search Our Full Inventory
//               <ArrowRight className="ml-2 h-4 w-4" />
//             </Button>
//           </Link>
//         </div>
//       </div>
//     </section>
//   );
// };

// export default FeaturedVehicles;

import { ArrowRight, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import VehicleCard from "./VehicleCard";
import { Button } from "@/components/ui/button";
import { usePopularVehicles } from "@/hooks/useApi";

const FeaturedVehicles = () => {
  const { data, isLoading, error } = usePopularVehicles(8);
  
  const featuredVehicles = data?.recommendations?.slice(0, 4) || [];

  return (
    <section className="py-24 bg-background relative overflow-hidden">
      {/* Subtle background decoration */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-3xl h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />
      <div className="absolute top-1/2 -right-64 w-80 h-80 bg-accent/3 rounded-full blur-3xl" />

      <div className="container mx-auto px-4 relative">
        {/* Section Header */}
        <div className="text-center mb-14">
          <span className="text-[10px] tracking-[0.2em] text-accent uppercase mb-4 block">
            Hand-picked selection
          </span>
          <h2 className="font-poppins text-3xl font-bold text-foreground tracking-tight mb-4">
            Featured Vehicles
          </h2>
          <p className="text-muted-foreground">
            Discover our most exclusive listings, carefully selected for
            quality and value.
          </p>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-accent" />
            <span className="ml-3 text-muted-foreground">Loading featured vehicles...</span>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="text-center py-20">
            <p className="text-muted-foreground">Unable to load vehicles. Please try again later.</p>
          </div>
        )}

        {/* Vehicle Grid */}
        {!isLoading && !error && featuredVehicles.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {featuredVehicles.map((item, index) => (
              <div
                key={item.vehicle.vehicle_id}
                className="animate-fade-in opacity-0"
                style={{ animationDelay: `${0.1 + index * 0.1}s`, animationFillMode: 'forwards' }}
              >
                <VehicleCard vehicle={item.vehicle} />
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && featuredVehicles.length === 0 && (
          <div className="text-center py-20">
            <p className="text-muted-foreground">No featured vehicles available at the moment.</p>
          </div>
        )}

        {/* Bottom CTA */}
        <div className="mt-20 text-center">
          <p className="text-muted-foreground mb-8">
            Looking for something specific? We can help you find it.
          </p>
          <Link to="/search">
            <Button
              size="lg"
              className="bg-[#0E317D] hover:bg-[#0E317D]/90 text-white font-body tracking-wide px-8 h-14 rounded-sm shadow-soft hover:shadow-elegant transition-all duration-500"
            >
              Search Our Full Inventory
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
};

export default FeaturedVehicles;