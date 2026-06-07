/**
 * Full Page Chat Component
 * Provides a dedicated chat experience with conversation history
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, Loader2, Car, Plus, ExternalLink
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  chatApi, Vehicle,
  formatPrice, formatMileage, getCurrentUser
} from '@/lib/api';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import Header from '@/components/Header';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  vehicles?: Vehicle[];
  timestamp: Date;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const user = getCurrentUser();

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Load welcome message for new conversation
  useEffect(() => {
    if (messages.length === 0 && !sessionId) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: "Hello! 👋 I'm your AI car shopping assistant. I can help you:\n\n• Find vehicles that match your needs and budget\n• Compare different makes and models\n• Answer questions about features and specifications\n• Provide personalized recommendations\n\nWhat kind of car are you looking for today?",
        timestamp: new Date()
      }]);
    }
  }, [messages.length, sessionId]);

  const startNewConversation = () => {
    // Clear the server-side session (history + profile) for a fresh start.
    if (sessionId) {
      chatApi.reset(sessionId).catch(() => { /* ignore — local reset is enough */ });
    }
    setSessionId(null);
    setMessages([]);
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await chatApi.sendMessage(userMessage.content, sessionId || undefined);

      // Server assigns a session_id on the first turn; reuse it for context.
      if (response.session_id) {
        setSessionId(response.session_id);
      }

      const assistantMessage: Message = {
        id: `${Date.now()}-a`,
        role: 'assistant',
        content: response.answer,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: "I'm sorry, I encountered an error. Please try again.",
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, sessionId]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Quick suggestion prompts
  const suggestions = [
    "I'm looking for a reliable SUV under $30,000",
    "What are the best fuel-efficient sedans?",
    "Show me luxury cars with low mileage",
    "Compare Honda Accord vs Toyota Camry",
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      
      <div className="flex-1 flex overflow-hidden">
        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col">
          {/* Chat Header */}
          <div className="h-14 border-b flex items-center px-4 gap-3">
            <Avatar className="h-8 w-8 bg-primary">
              <AvatarFallback className="bg-primary text-primary-foreground">
                <Car className="h-4 w-4" />
              </AvatarFallback>
            </Avatar>
            <div className="flex-1">
              <h2 className="font-semibold">Car Shopping Assistant</h2>
              <p className="text-xs text-muted-foreground">Powered by AI</p>
            </div>
            <Button
              onClick={startNewConversation}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              New Chat
            </Button>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 p-4" ref={scrollRef}>
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((message) => (
                <div key={message.id} className={cn(
                  "flex gap-4",
                  message.role === 'user' ? "flex-row-reverse" : "flex-row"
                )}>
                  <Avatar className={cn(
                    "h-10 w-10 flex-shrink-0",
                    message.role === 'user' ? "bg-secondary" : "bg-primary"
                  )}>
                    <AvatarFallback className={cn(
                      message.role === 'user' 
                        ? "bg-secondary text-secondary-foreground" 
                        : "bg-primary text-primary-foreground"
                    )}>
                      {message.role === 'user' 
                        ? (user?.full_name?.charAt(0) || user?.email?.charAt(0) || 'U') 
                        : <Car className="h-5 w-5" />}
                    </AvatarFallback>
                  </Avatar>
                  
                  <div className={cn(
                    "max-w-[80%] space-y-2",
                    message.role === 'user' && "text-right"
                  )}>
                    <div className={cn(
                      "inline-block rounded-lg px-4 py-3",
                      message.role === 'user' 
                        ? "bg-primary text-primary-foreground" 
                        : "bg-muted"
                    )}>
                      <p className="whitespace-pre-wrap text-left">{message.content}</p>
                    </div>
                    
                    {/* Vehicle Cards */}
                    {message.vehicles && message.vehicles.length > 0 && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                        {message.vehicles.slice(0, 4).map((vehicle) => (
                          <Link
                            key={vehicle.id}
                            to={`/vehicles/${vehicle.id}`}
                            className="block p-3 rounded-lg border bg-card hover:bg-accent transition-colors text-left"
                          >
                            <div className="flex gap-3">
                              {vehicle.image_url ? (
                                <img
                                  src={vehicle.image_url}
                                  alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                                  className="w-24 h-18 object-cover rounded"
                                  onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = 'none';
                                  }}
                                />
                              ) : (
                                <div className="w-24 h-18 bg-muted rounded flex items-center justify-center">
                                  <Car className="h-8 w-8 text-muted-foreground" />
                                </div>
                              )}
                              <div className="flex-1 min-w-0">
                                <p className="font-medium text-sm">
                                  {vehicle.year} {vehicle.make} {vehicle.model}
                                </p>
                                {vehicle.trim && (
                                  <p className="text-xs text-muted-foreground">{vehicle.trim}</p>
                                )}
                                <p className="text-sm font-semibold text-primary mt-1">
                                  {formatPrice(vehicle.price)}
                                </p>
                                {vehicle.mileage && (
                                  <p className="text-xs text-muted-foreground">
                                    {formatMileage(vehicle.mileage)}
                                  </p>
                                )}
                              </div>
                              <ExternalLink className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                            </div>
                          </Link>
                        ))}
                      </div>
                    )}
                    
                    <p className="text-xs text-muted-foreground">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              ))}
              
              {isLoading && (
                <div className="flex gap-4">
                  <Avatar className="h-10 w-10 bg-primary">
                    <AvatarFallback className="bg-primary text-primary-foreground">
                      <Car className="h-5 w-5" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="bg-muted rounded-lg px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">Thinking...</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Suggestions for new conversations */}
              {messages.length <= 1 && !isLoading && (
                <div className="mt-8">
                  <p className="text-sm text-muted-foreground text-center mb-4">
                    Try asking:
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {suggestions.map((suggestion, i) => (
                      <Button
                        key={i}
                        variant="outline"
                        size="sm"
                        className="text-sm"
                        onClick={() => {
                          setInput(suggestion);
                          inputRef.current?.focus();
                        }}
                      >
                        {suggestion}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Input Area */}
          <div className="border-t p-4">
            <div className="max-w-3xl mx-auto flex gap-3">
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message..."
                disabled={isLoading}
                className="flex-1"
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                size="icon"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
