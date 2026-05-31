import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, X, Plus, Camera } from "lucide-react";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { brands, fuelTypes, transmissions } from "@/data/vehicles";

const SellPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [images, setImages] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleImageUpload = () => {
    const mockImages = [
      "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=400&h=300&fit=crop&q=80",
      "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=400&h=300&fit=crop&q=80",
    ];
    if (images.length < 6) {
      setImages([...images, mockImages[images.length % 2]]);
    }
  };

  const removeImage = (index: number) => {
    setImages(images.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    setTimeout(() => {
      setIsSubmitting(false);
      toast({
        title: "Listing submitted successfully!",
        description: "Your listing will be reviewed within 24 hours.",
      });
      navigate("/");
    }, 1500);
  };

  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden" style={{ backgroundColor: "#1a5cf5" }}>
      {/* Large circle top-left (cut off) */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "520px", height: "520px", top: "-180px", left: "-160px", backgroundColor: "#0e2d8f", opacity: 0.85 }} />
      {/* Medium circle top-right (cut off) */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "300px", height: "300px", top: "-80px", right: "-60px", backgroundColor: "#0c2580", opacity: 0.7 }} />
      {/* Large semicircle bottom-right */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "680px", height: "680px", bottom: "-280px", right: "-180px", backgroundColor: "#1035a8", opacity: 0.85 }} />
      {/* Medium circle bottom-left (cut off) */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "360px", height: "360px", bottom: "-120px", left: "-100px", backgroundColor: "#0c2a9e", opacity: 0.65 }} />
      {/* Medium circle left-center */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "200px", height: "200px", top: "42%", left: "-70px", backgroundColor: "#0e2d8f", opacity: 0.55 }} />
      {/* Small dot top-center */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "52px", height: "52px", top: "60px", left: "44%", backgroundColor: "#0e2470", opacity: 0.9 }} />
      {/* Small dot right-center */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "36px", height: "36px", top: "38%", right: "12%", backgroundColor: "#0a1f6e", opacity: 0.75 }} />
      {/* Tiny dot top-left area */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "22px", height: "22px", top: "22%", left: "18%", backgroundColor: "#0a1f6e", opacity: 0.6 }} />
      {/* Tiny dot bottom-center */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "18px", height: "18px", bottom: "18%", left: "52%", backgroundColor: "#0c2580", opacity: 0.65 }} />
      {/* Small circle mid-right */}
      <div className="pointer-events-none absolute rounded-full"
        style={{ width: "110px", height: "110px", top: "55%", right: "-30px", backgroundColor: "#0e2d8f", opacity: 0.6 }} />

      <Header />
      <main className="flex-1 pt-28 pb-16 relative z-10">
        <div className="container mx-auto px-4 max-w-3xl">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="font-poppins text-3xl md:text-4xl font-semibold text-white mb-3">
              Sell Your Car
            </h1>
            <p className="text-blue-100 text-lg">
              Fill in the details about your car to find a buyer quickly
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-10">
            {/* Images Section */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2.5 bg-accent/10 rounded-xl">
                  <Camera className="h-5 w-5 text-accent" />
                </div>
                <div>
                  <Label className="text-lg font-semibold">Vehicle Photos</Label>
                  <p className="text-sm text-muted-foreground">Add up to 6 photos of your vehicle</p>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                {images.map((img, index) => (
                  <div
                    key={index}
                    className="relative aspect-[4/3] rounded-xl overflow-hidden bg-secondary group"
                  >
                    <img src={img} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeImage(index)}
                      className="absolute top-2 right-2 p-1.5 bg-background/90 rounded-full opacity-0 group-hover:opacity-100 hover:bg-destructive hover:text-destructive-foreground transition-all"
                    >
                      <X className="h-4 w-4" />
                    </button>
                    {index === 0 && (
                      <span className="absolute bottom-2 left-2 px-2 py-1 bg-accent text-accent-foreground text-xs font-medium rounded-md">
                        Cover
                      </span>
                    )}
                  </div>
                ))}
                {images.length < 6 && (
                  <button
                    type="button"
                    onClick={handleImageUpload}
                    className="aspect-[4/3] rounded-xl border-2 border-dashed border-border hover:border-accent flex flex-col items-center justify-center gap-2 text-muted-foreground hover:text-accent transition-all bg-secondary/30"
                  >
                    <Plus className="h-6 w-6" />
                    <span className="text-sm font-medium">Add Photo</span>
                  </button>
                )}
              </div>
            </div>

            {/* Basic Info */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <h3 className="font-poppins text-lg font-semibold mb-6">Basic Information</h3>

              <div className="grid sm:grid-cols-2 gap-5">
                <div className="space-y-2">
                  <Label htmlFor="brand">Brand *</Label>
                  <Select required>
                    <SelectTrigger className="h-12 rounded-xl">
                      <SelectValue placeholder="Select brand" />
                    </SelectTrigger>
                    <SelectContent>
                      {brands.map((brand) => (
                        <SelectItem key={brand} value={brand}>
                          {brand}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="model">Model *</Label>
                  <Input id="model" placeholder="e.g., Camry, CR-V..." required className="h-12 rounded-xl" />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="year">Year *</Label>
                  <Select required>
                    <SelectTrigger className="h-12 rounded-xl">
                      <SelectValue placeholder="Select year" />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 15 }, (_, i) => 2024 - i).map((year) => (
                        <SelectItem key={year} value={year.toString()}>
                          {year}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="price">Price ($) *</Label>
                  <Input id="price" type="number" placeholder="45000" required className="h-12 rounded-xl" />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mileage">Mileage (km) *</Label>
                  <Input id="mileage" type="number" placeholder="10000" required className="h-12 rounded-xl" />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="fuel">Fuel Type *</Label>
                  <Select required>
                    <SelectTrigger className="h-12 rounded-xl">
                      <SelectValue placeholder="Select fuel type" />
                    </SelectTrigger>
                    <SelectContent>
                      {fuelTypes.map((fuel) => (
                        <SelectItem key={fuel} value={fuel}>
                          {fuel}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="transmission">Transmission *</Label>
                  <Select required>
                    <SelectTrigger className="h-12 rounded-xl">
                      <SelectValue placeholder="Select transmission" />
                    </SelectTrigger>
                    <SelectContent>
                      {transmissions.map((trans) => (
                        <SelectItem key={trans} value={trans}>
                          {trans}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="color">Color *</Label>
                  <Input id="color" placeholder="e.g., White, Black..." required className="h-12 rounded-xl" />
                </div>
              </div>
            </div>

            {/* Description */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <h3 className="font-poppins text-lg font-semibold mb-6">Description</h3>
              <Textarea
                id="description"
                placeholder="Describe the vehicle condition, maintenance history, notable features..."
                className="min-h-[140px] rounded-xl resize-none"
              />
            </div>

            {/* Contact Info */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <h3 className="font-poppins text-lg font-semibold mb-6">Contact Information</h3>

              <div className="grid sm:grid-cols-2 gap-5">
                <div className="space-y-2">
                  <Label htmlFor="name">Full Name *</Label>
                  <Input id="name" placeholder="John Doe" required className="h-12 rounded-xl" />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number *</Label>
                  <Input id="phone" type="tel" placeholder="+1 555-0123" required className="h-12 rounded-xl" />
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="location">Location *</Label>
                  <Input id="location" placeholder="City, State" required className="h-12 rounded-xl" />
                </div>
              </div>
            </div>

            {/* Submit */}
            <div className="pt-4">
              <Button
                type="submit"
                className="w-full h-14 rounded-xl text-base bg-[#0E317D] hover:bg-[#0C2868] hover:shadow-lg text-white font-semibold transition-all duration-200"
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <Upload className="h-5 w-5 mr-2 animate-pulse" />
                    Submitting...
                  </>
                ) : (
                  "Submit Listing"
                )}
              </Button>
            </div>
          </form>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default SellPage;