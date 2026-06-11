import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, ArrowLeft, ArrowRight, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { authApi, storeAuthData } from "@/lib/api";
import { useGoogleLogin } from "@react-oauth/google";


const LoginPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isLogin, setIsLogin] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Form fields
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    full_name: "",
    phone: "",
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.id]: e.target.value });
  };

  const handleGoogleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setIsLoading(true);
      try {
        const response = await authApi.socialLogin({
          provider: "google",
          token: tokenResponse.access_token,
        });
        storeAuthData(response);
        toast({
          title: "Logged in successfully!",
          description: `Welcome ${response.user.full_name || response.user.username}!`,
        });
        navigate("/");
      } catch (error: any) {
        const message = error?.response?.data?.detail || "Google authentication failed.";
        toast({
          title: "Error",
          description: message,
          variant: "destructive",
        });
      } finally {
        setIsLoading(false);
      }
    },
    onError: () => {
      toast({
        title: "Google Sign-In Failed",
        description: "Could not authenticate with Google. Please try again.",
        variant: "destructive",
      });
    },
  });


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      if (isLogin) {
        const response = await authApi.login(formData.email, formData.password);
        storeAuthData(response);
        toast({
          title: "Welcome back!",
          description: `Logged in as ${response.user.username || response.user.email}`,
        });
      } else {
        const response = await authApi.register({
          username: formData.username || formData.email.split('@')[0],
          email: formData.email,
          password: formData.password,
          full_name: formData.full_name,
          phone: formData.phone,
        });
        storeAuthData(response);
        toast({
          title: "Account created!",
          description: "Welcome to CarMarket!",
        });
      }
      navigate("/");
    } catch (error: any) {
      const message = error?.response?.data?.detail || "Authentication failed. Please try again.";
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left side - Form */}
      <div className="flex-1 relative flex items-center justify-center p-8">

        {/* Back to Home */}
        <Link
          to="/"
          className="absolute top-4 left-8 inline-flex items-center gap-1.5 text-sm font-medium text-slate-800 transition-all duration-200 hover:text-[#A87601] hover:underline hover:scale-105 z-10"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Home page
        </Link>

        {/* Thêm mt-12 để đảm bảo form luôn cách xa nút Back ở phía trên */}
        <div className="w-full max-w-md space-y-8 mt-12">
          {/* Logo */}
          <Link to="/" className="inline-flex items-center gap-2 group">
            <span className="font-body text-4xl font-semibold tracking-tight text-foreground">
              Car<span className="text-[#A87601]">Market</span>
            </span>
          </Link>

          {/* Header */}
          <div>
            <h1 className="font-poppins text-3xl font-semibold text-foreground mb-2">
              {isLogin ? "Welcome back" : "Create account"}
            </h1>
            <p className="text-muted-foreground">
              {isLogin
                ? "Sign in to access your account"
                : "Start your journey with us today"}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name</Label>
                <Input
                  id="full_name"
                  placeholder="John Doe"
                  required
                  className="h-12 rounded-xl"
                  value={formData.full_name}
                  onChange={handleInputChange}
                />
              </div>
            )}

            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  placeholder="johndoe"
                  required
                  className="h-12 rounded-xl"
                  value={formData.username}
                  onChange={handleInputChange}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">{isLogin ? "Email or Username" : "Email"}</Label>
              <Input
                id="email"
                type={isLogin ? "text" : "email"}
                placeholder="you@example.com"
                required
                className="h-12 rounded-xl"
                value={formData.email}
                onChange={handleInputChange}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  required
                  className="h-12 rounded-xl pr-12"
                  value={formData.password}
                  onChange={handleInputChange}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {isLogin && (
              <div className="text-right">
                <a href="#" className="text-sm text-muted-foreground hover:text-accent transition-colors">
                  Forgot password?
                </a>
              </div>
            )}

            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="phone">Phone Number (optional)</Label>
                <Input
                  id="phone"
                  type="tel"
                  placeholder="+1 555-0123"
                  className="h-12 rounded-xl"
                  value={formData.phone}
                  onChange={handleInputChange}
                />
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-12 rounded-xl bg-[#A87601] hover:bg-[#A87601]/85 hover:shadow-lg text-white font-medium text-base transition-all duration-200"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  {isLogin ? "Sign In" : "Create Account"}
                  <ArrowRight className="ml-2 h-5 w-5" />
                </>
              )}
            </Button>
          </form>

          {/* Divider */}
          <div className="relative">
            <Separator />
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-4 text-sm text-muted-foreground">
              or continue with
            </span>
          </div>

          {/* Social Login */}
          <div className="grid grid-cols-1 gap-4">
            <Button
              variant="outline"
              className="h-12 rounded-xl flex items-center justify-center gap-2 border border-input bg-background hover:bg-accent hover:text-accent-foreground transition-all duration-200"
              type="button"
              onClick={() => handleGoogleLogin()}
              disabled={isLoading}
            >
              <img
                src="https://www.google.com/favicon.ico"
                alt="Google"
                className="h-5 w-5"
              />
              Continue with Google
            </Button>
          </div>

          {/* Toggle */}
          <p className="text-center text-muted-foreground">
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <button
              type="button"
              onClick={() => setIsLogin(!isLogin)}
              className="text-[#A87601] font-medium hover:underline"
            >
              {isLogin ? "Sign Up" : "Sign In"}
            </button>
          </p>
        </div>
      </div>

      {/* Right side - Image */}
      <div className="hidden lg:block flex-1 relative overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200&h=1600&fit=crop&q=80"
          alt="Luxury car"
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/60 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />

        {/* Content overlay */}
        <div className="absolute bottom-16 left-16 right-16">
          <h2 className="font-poppins text-4xl font-semibold text-foreground mb-4">
            Discover Your <span className="text-[#A87601]">Dream Car</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-md">
            Join thousands of satisfied buyers and sellers in our premium automotive marketplace.
          </p>
        </div>
      </div>


    </div>
  );
};

export default LoginPage;