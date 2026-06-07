/**
 * Custom hooks for API data fetching using React Query
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  vehiclesApi,
  recommendationsApi,
  interactionsApi,
  authApi,
  SearchParams,
  SearchResponse,
  Vehicle,
  VehicleDetail,
  RecommendationResponse,
  Interaction,
  Favorite,
  User,
  AuthResponse,
  Review,
  Seller,
  storeAuthData,
  trackVehicleView,
} from '@/lib/api';

// ============== QUERY KEYS ==============

export const queryKeys = {
  vehicles: {
    all: ['vehicles'] as const,
    search: (params: SearchParams) => ['vehicles', 'search', params] as const,
    detail: (id: string) => ['vehicles', id] as const,
    listings: (limit: number, offset: number) => ['vehicles', 'listings', limit, offset] as const,
    reviews: (id: string) => ['vehicles', 'reviews', id] as const,
    seller: (id: string) => ['vehicles', 'seller', id] as const,
  },
  recommendations: {
    all: ['recommendations'] as const,
    similar: (vehicleId: string) => ['recommendations', 'similar', vehicleId] as const,
    personalized: () => ['recommendations', 'personalized'] as const,
    popular: () => ['recommendations', 'popular'] as const,
    hybrid: () => ['recommendations', 'hybrid'] as const,
  },
  interactions: {
    all: ['interactions'] as const,
    history: (params?: { limit?: number; interaction_type?: string }) =>
      ['interactions', 'history', params] as const,
    favorites: () => ['interactions', 'favorites'] as const,
  },
  user: {
    current: ['user', 'me'] as const,
  },
};

// ============== VEHICLE HOOKS ==============

/**
 * Search vehicles with filters
 */
export function useVehicleSearch(params: SearchParams, enabled = true) {
  return useQuery<SearchResponse>({
    queryKey: queryKeys.vehicles.search(params),
    queryFn: () => vehiclesApi.search(params),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Get vehicle details by ID
 */
export function useVehicleDetail(vehicleId: string | undefined) {
  return useQuery<VehicleDetail>({
    queryKey: queryKeys.vehicles.detail(vehicleId ?? ''),
    queryFn: async () => {
      if (!vehicleId) throw new Error('Vehicle ID is required');
      const detail = await vehiclesApi.getById(vehicleId);
      // Track view
      trackVehicleView(vehicleId);
      return detail;
    },
    enabled: !!vehicleId,
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

/**
 * Get featured/latest listings
 */
export function useVehicleListings(limit = 10, offset = 0) {
  return useQuery<Vehicle[]>({
    queryKey: queryKeys.vehicles.listings(limit, offset),
    queryFn: () => vehiclesApi.getListings(limit, offset),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Get vehicle reviews
 */
export function useVehicleReviews(vehicleId: string | undefined, limit = 10) {
  return useQuery<Review[]>({
    queryKey: queryKeys.vehicles.reviews(vehicleId ?? ''),
    queryFn: () => vehiclesApi.getReviews(vehicleId!, limit),
    enabled: !!vehicleId,
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

/**
 * Get vehicle seller info
 */
export function useVehicleSeller(vehicleId: string | undefined) {
  return useQuery<Seller | null>({
    queryKey: queryKeys.vehicles.seller(vehicleId ?? ''),
    queryFn: () => vehiclesApi.getSeller(vehicleId!),
    enabled: !!vehicleId,
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

// ============== RECOMMENDATION HOOKS ==============

/**
 * Get similar vehicles based on item-based CF
 */
export function useSimilarVehicles(vehicleId: string | undefined, limit = 6) {
  return useQuery<RecommendationResponse>({
    queryKey: queryKeys.recommendations.similar(vehicleId ?? ''),
    queryFn: () => recommendationsApi.getSimilar(vehicleId!, limit),
    enabled: !!vehicleId,
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

/**
 * Get personalized recommendations for logged-in user
 */
export function usePersonalizedRecommendations(limit = 20) {
  return useQuery<RecommendationResponse>({
    queryKey: queryKeys.recommendations.personalized(),
    queryFn: () => recommendationsApi.getPersonalized(limit),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Get popular vehicles
 */
export function usePopularVehicles(limit = 20) {
  return useQuery<RecommendationResponse>({
    queryKey: queryKeys.recommendations.popular(),
    queryFn: () => recommendationsApi.getPopular(limit),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Get hybrid recommendations
 */
export function useHybridRecommendations(limit = 20) {
  return useQuery<RecommendationResponse>({
    queryKey: queryKeys.recommendations.hybrid(),
    queryFn: () => recommendationsApi.getHybrid(limit),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// ============== INTERACTION HOOKS ==============

/**
 * Track user interaction
 */
export function useTrackInteraction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: interactionsApi.track,
    onSuccess: () => {
      // Invalidate interaction history
      queryClient.invalidateQueries({ queryKey: queryKeys.interactions.all });
    },
  });
}

/**
 * Get user's interaction history
 */
export function useInteractionHistory(params?: { limit?: number; interaction_type?: string }) {
  return useQuery<Interaction[]>({
    queryKey: queryKeys.interactions.history(params),
    queryFn: () => interactionsApi.getHistory(params),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
}

/**
 * Get user's favorites
 */
export function useFavorites() {
  return useQuery<Favorite[]>({
    queryKey: queryKeys.interactions.favorites(),
    queryFn: () => interactionsApi.getFavorites(),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
}

/**
 * Add vehicle to favorites
 */
export function useAddFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: interactionsApi.addFavorite,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.interactions.favorites() });
    },
  });
}

/**
 * Remove vehicle from favorites
 */
export function useRemoveFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: interactionsApi.removeFavorite,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.interactions.favorites() });
    },
  });
}

// ============== AUTH HOOKS ==============

/**
 * Register new user
 */
export function useRegister() {
  return useMutation({
    mutationFn: authApi.register,
    onSuccess: (data: AuthResponse) => {
      storeAuthData(data);
    },
  });
}

/**
 * Login user
 */
export function useLogin() {
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.login(username, password),
    onSuccess: (data: AuthResponse) => {
      storeAuthData(data);
    },
  });
}

/**
 * Get current user
 */
export function useCurrentUser() {
  return useQuery<User>({
    queryKey: queryKeys.user.current,
    queryFn: authApi.getMe,
    retry: false,
    staleTime: 1000 * 60 * 30, // 30 minutes
  });
}

/**
 * Logout user
 */
export function useLogout() {
  const queryClient = useQueryClient();

  return () => {
    authApi.logout();
    queryClient.clear();
    window.location.href = '/';
  };
}

// ============== CHAT HOOKS ==============
// The chatbot is now the agentic POST /api/v1/chat (in-memory sessions). It has
// no conversation-list / message-history / delete endpoints, so the old
// useChatConversations / useChatMessages / useSendMessage / useDeleteConversation
// hooks were removed. Components call chatApi.sendMessage / chatApi.reset directly
// (see ChatPage.tsx and ChatPopup.tsx) and keep session_id in local state.
