/**
 * Chat Popup Component - Floating chat bubble with expandable chat window
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MessageCircle, X, Send, Loader2, Car, ChevronDown, Maximize2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { chatApi, Vehicle, formatPrice, isAuthenticated } from '@/lib/api';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  vehicles?: Vehicle[];
  timestamp: Date;
}

export default function ChatPopup() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showVehicles, setShowVehicles] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Load welcome message
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: "Hi there! 👋 I'm your AI car assistant. I can help you find the perfect vehicle. Tell me what you're looking for - your budget, preferred type, features, or any other requirements!",
        timestamp: new Date()
      }]);
    }
  }, [isOpen, messages.length]);

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

  const clearChat = () => {
    // Best-effort: clear the server-side session (history + profile) too.
    if (sessionId) {
      chatApi.reset(sessionId).catch(() => { /* ignore — local reset is enough */ });
    }
    setMessages([]);
    setSessionId(null);
  };

  const toggleVehicles = (messageId: string) => {
    setShowVehicles(prev => prev === messageId ? null : messageId);
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "fixed bottom-6 right-6 z-50 rounded-full p-4 shadow-lg transition-all duration-300",
          "bg-primary text-primary-foreground hover:bg-primary/90",
          "flex items-center justify-center",
          isOpen && "rotate-90"
        )}
        aria-label={isOpen ? "Close chat" : "Open chat"}
      >
        {isOpen ? (
          <X className="h-6 w-6" />
        ) : (
          <MessageCircle className="h-6 w-6" />
        )}
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div className={cn(
          "fixed bottom-24 right-6 z-50 w-96 max-w-[calc(100vw-3rem)]",
          "bg-background border rounded-lg shadow-xl",
          "flex flex-col",
          "animate-in slide-in-from-bottom-5 fade-in duration-300"
        )}
        style={{ height: '500px', maxHeight: 'calc(100vh - 10rem)' }}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b bg-muted/50 rounded-t-lg">
            <div className="flex items-center gap-3">
              <Avatar className="h-10 w-10 bg-primary">
                <AvatarFallback className="bg-primary text-primary-foreground">
                  <Car className="h-5 w-5" />
                </AvatarFallback>
              </Avatar>
              <div>
                <h3 className="font-semibold">Car Assistant</h3>
                <p className="text-xs text-muted-foreground">Ask me anything about cars</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={clearChat}
                title="Clear chat"
                className="h-8 w-8"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Link to="/chat">
                <Button
                  variant="ghost"
                  size="icon"
                  title="Open full page"
                  className="h-8 w-8"
                >
                  <Maximize2 className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 p-4" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((message) => (
                <div key={message.id}>
                  <div className={cn(
                    "flex gap-3",
                    message.role === 'user' ? "flex-row-reverse" : "flex-row"
                  )}>
                    <Avatar className={cn(
                      "h-8 w-8 flex-shrink-0",
                      message.role === 'user' ? "bg-secondary" : "bg-primary"
                    )}>
                      <AvatarFallback className={cn(
                        message.role === 'user' 
                          ? "bg-secondary text-secondary-foreground" 
                          : "bg-primary text-primary-foreground"
                      )}>
                        {message.role === 'user' ? 'U' : <Car className="h-4 w-4" />}
                      </AvatarFallback>
                    </Avatar>
                    <div className={cn(
                      "max-w-[80%] rounded-lg px-3 py-2",
                      message.role === 'user' 
                        ? "bg-primary text-primary-foreground" 
                        : "bg-muted"
                    )}>
                      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      
                      {/* Vehicle suggestions */}
                      {message.vehicles && message.vehicles.length > 0 && (
                        <div className="mt-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleVehicles(message.id)}
                            className="h-auto p-1 text-xs gap-1"
                          >
                            <Car className="h-3 w-3" />
                            {message.vehicles.length} vehicle{message.vehicles.length > 1 ? 's' : ''} found
                            <ChevronDown className={cn(
                              "h-3 w-3 transition-transform",
                              showVehicles === message.id && "rotate-180"
                            )} />
                          </Button>
                          
                          {showVehicles === message.id && (
                            <div className="mt-2 space-y-2">
                              {message.vehicles.slice(0, 3).map((vehicle) => (
                                <Link
                                  key={vehicle.id}
                                  to={`/vehicles/${vehicle.id}`}
                                  className="block p-2 rounded bg-background border hover:bg-accent transition-colors"
                                  onClick={() => setIsOpen(false)}
                                >
                                  <div className="flex gap-2">
                                    {vehicle.image_url && (
                                      <img
                                        src={vehicle.image_url}
                                        alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                                        className="w-16 h-12 object-cover rounded"
                                        onError={(e) => {
                                          (e.target as HTMLImageElement).src = '/placeholder.svg';
                                        }}
                                      />
                                    )}
                                    <div className="flex-1 min-w-0">
                                      <p className="text-xs font-medium truncate">
                                        {vehicle.year} {vehicle.make} {vehicle.model}
                                      </p>
                                      <p className="text-xs text-muted-foreground">
                                        {formatPrice(vehicle.price)}
                                      </p>
                                    </div>
                                  </div>
                                </Link>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              
              {isLoading && (
                <div className="flex gap-3">
                  <Avatar className="h-8 w-8 bg-primary">
                    <AvatarFallback className="bg-primary text-primary-foreground">
                      <Car className="h-4 w-4" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="bg-muted rounded-lg px-3 py-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="p-4 border-t">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask about cars..."
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
            {!isAuthenticated() && (
              <p className="text-xs text-muted-foreground mt-2 text-center">
                <Link to="/login" className="underline hover:text-primary">Sign in</Link> to save your conversations
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
