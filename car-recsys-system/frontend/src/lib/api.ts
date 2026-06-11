// --- Chat API ---
// Backend is the agentic LangGraph at POST /api/v1/chat. Sessions are in-memory
// per session_id (the server keeps history + profile), so the client only sends
// {session_id?, message, reset?} and gets back {session_id, answer}. There is no
// server-side conversation list / message history endpoint anymore.
export interface ChatResponse {
  session_id: string;
  answer: string;
}

export const chatApi = {
  async sendMessage(message: string, sessionId?: string): Promise<ChatResponse> {
    const response = await api.post("/chat", { message, session_id: sessionId });
    return response.data;
  },
  // Clear the server-side session (history + slot-filled profile) for a fresh start.
  async reset(sessionId: string): Promise<ChatResponse> {
    const response = await api.post("/chat", { message: "reset", session_id: sessionId, reset: true });
    return response.data;
  },
};

export function formatMileage(mileage?: number | null): string {
  if (mileage == null || Number.isNaN(mileage)) return "N/A";
  return `${mileage.toLocaleString()} mi`;
}

export function getCurrentUser(): User | null {
  return getAuthData()?.user ?? null;
}
import axios from "axios";

const API_BASE_URL = "/api/v1";
const AUTH_STORAGE_KEY = "car_recsys_auth";

export interface Vehicle {
  vehicle_id: string;
  title?: string;
  brand?: string;
  car_model?: string;
  car_name?: string;
  price?: number | null;
  monthly_payment?: number | null;
  mileage?: number | null;
  mileage_str?: string;
  exterior_color?: string;
  interior_color?: string;
  drivetrain?: string;
  mpg?: string;
  fuel_type?: string;
  transmission?: string;
  engine?: string;
  condition?: string;
  accidents_damage?: string;
  one_owner?: boolean | null;
  car_rating?: number | null;
  percentage_recommend?: number | null;
  comfort_rating?: number | null;
  interior_rating?: number | null;
  performance_rating?: number | null;
  value_rating?: number | null;
  exterior_rating?: number | null;
  reliability_rating?: number | null;
  vehicle_url?: string;
  total_images?: number | null;
  image_url?: string;
  images?: string[];
  features?: string[];
}

export interface VehicleDetail extends Vehicle {}

export interface SearchParams {
  query?: string;
  condition?: string;
  brand?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  mileage_max?: number;
  fuel_type?: string;
  transmission?: string;
  drivetrain?: string;
  exterior_color?: string;
  min_rating?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface SearchResponse {
  results: Vehicle[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RecommendationItem {
  vehicle: Vehicle;
  score: number;
  reason?: string;
}

export interface RecommendationResponse {
  recommendations: RecommendationItem[];
  total: number;
  algorithm: string;
}

export interface Interaction {
  id: string;
  user_id: string;
  vehicle_id: string;
  interaction_type: string;
  session_id?: string;
  interaction_score?: number;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface Favorite {
  id: string;
  user_id: string;
  vehicle_id: string;
  created_at: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  phone?: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearAuthData();
    }
    return Promise.reject(error);
  }
);

export function getAuthData(): AuthResponse | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthResponse) : null;
  } catch {
    return null;
  }
}

export function getAuthToken(): string | null {
  return getAuthData()?.access_token ?? null;
}

export function storeAuthData(data: AuthResponse): void {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data));
}

export function clearAuthData(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAuthToken());
}

export function formatPrice(price?: number | null): string {
  if (price == null || Number.isNaN(price)) {
    return "Price on request";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(price);
}

export const vehiclesApi = {
  async search(params: SearchParams): Promise<SearchResponse> {
    const response = await api.get<SearchResponse>("/search", { params });
    return response.data;
  },

  async getById(vehicleId: string): Promise<VehicleDetail> {
    const response = await api.get<VehicleDetail>(`/listing/${vehicleId}`);
    return response.data;
  },

  async getListings(limit = 10, offset = 0): Promise<Vehicle[]> {
    const response = await api.get<Vehicle[]>("/listings", {
      params: { limit, offset },
    });
    return response.data;
  },
};

export const recommendationsApi = {
  async getSimilar(vehicleId: string, limit = 6): Promise<RecommendationResponse> {
    const response = await api.get<RecommendationResponse>(`/reco/similar/${vehicleId}`, {
      params: { limit },
    });
    return response.data;
  },

  async getPersonalized(limit = 20): Promise<RecommendationResponse> {
    const response = await api.get<RecommendationResponse>("/reco/personalized", {
      params: { limit },
    });
    return response.data;
  },

  async getPopular(limit = 20): Promise<RecommendationResponse> {
    const response = await api.get<RecommendationResponse>("/reco/popular", {
      params: { limit },
    });
    return response.data;
  },

  async getHybrid(limit = 20): Promise<RecommendationResponse> {
    const response = await api.get<RecommendationResponse>("/reco/hybrid", {
      params: { limit },
    });
    return response.data;
  },
};

export const interactionsApi = {
  async track(payload: {
    vehicle_id: string;
    interaction_type: string;
    session_id?: string;
    interaction_score?: number;
    metadata?: Record<string, unknown>;
  }): Promise<Interaction> {
    const response = await api.post<Interaction>("/interactions/track", payload);
    return response.data;
  },

  async getHistory(params?: { limit?: number; interaction_type?: string }): Promise<Interaction[]> {
    const response = await api.get<Interaction[]>("/interactions/history", { params });
    return response.data;
  },

  async getFavorites(): Promise<Favorite[]> {
    const response = await api.get<Favorite[]>("/interactions/favorites");
    return response.data;
  },

  async addFavorite(vehicle_id: string): Promise<Favorite> {
    const response = await api.post<Favorite>("/interactions/favorites", { vehicle_id });
    return response.data;
  },

  async removeFavorite(vehicle_id: string): Promise<void> {
    await api.delete(`/interactions/favorites/${vehicle_id}`);
  },
};

export const authApi = {
  async register(payload: {
    username: string;
    email: string;
    password: string;
    full_name?: string;
    phone?: string;
  }): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>("/auth/register", payload);
    return response.data;
  },

  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>("/auth/login", { username, password });
    return response.data;
  },

  async getMe(): Promise<User> {
    const response = await api.get<User>("/auth/me");
    return response.data;
  },

  async socialLogin(payload: {
    provider: string;
    email: string;
    full_name?: string;
    token?: string;
  }): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>("/auth/social-login", payload);
    return response.data;
  },

  logout(): void {
    clearAuthData();
  },
};

function getSessionId(): string {
  const key = "car_recsys_session_id";
  const existing = sessionStorage.getItem(key);
  if (existing) {
    return existing;
  }
  const created = crypto.randomUUID();
  sessionStorage.setItem(key, created);
  return created;
}

function trackInteractionSafe(vehicleId: string, interactionType: string, interactionScore: number): void {
  if (!isAuthenticated()) {
    return;
  }

  interactionsApi
    .track({
      vehicle_id: vehicleId,
      interaction_type: interactionType,
      interaction_score: interactionScore,
      session_id: getSessionId(),
    })
    .catch(() => {
      // Do not interrupt UI for analytics/tracking failures.
    });
}

export function trackVehicleView(vehicleId: string): void {
  trackInteractionSafe(vehicleId, "view", 1);
}

export function trackVehicleClick(vehicleId: string): void {
  trackInteractionSafe(vehicleId, "click", 2);
}
