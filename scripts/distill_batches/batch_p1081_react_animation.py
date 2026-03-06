"""
Batch p1081: TypeScript/React production pairs - React Animation
Topics: Framer Motion, CSS transitions, layout animations, gestures, scroll animations
"""

PAIRS = [
    ("react/animation_framer_motion", r'''Build production animation patterns using Framer Motion in React/TypeScript including page transitions, list reordering, shared layout animations, and staggered entrance animations.''', r'''// components/AnimatedList.tsx
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";

// Staggered list entrance animation
interface AnimatedListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  keyExtractor: (item: T) => string;
  staggerDelay?: number;
}

function AnimatedList<T>({
  items,
  renderItem,
  keyExtractor,
  staggerDelay = 0.05,
}: AnimatedListProps<T>) {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: staggerDelay,
        delayChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20, scale: 0.95 },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: {
        type: "spring",
        stiffness: 300,
        damping: 24,
      },
    },
    exit: {
      opacity: 0,
      x: -100,
      transition: { duration: 0.2 },
    },
  };

  return (
    <motion.ul
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-2"
    >
      <AnimatePresence mode="popLayout">
        {items.map((item, index) => (
          <motion.li
            key={keyExtractor(item)}
            variants={itemVariants}
            exit="exit"
            layout
            className="bg-white rounded-lg shadow p-4"
          >
            {renderItem(item, index)}
          </motion.li>
        ))}
      </AnimatePresence>
    </motion.ul>
  );
}

// Page transition wrapper
interface PageTransitionProps {
  children: React.ReactNode;
  direction?: "left" | "right" | "up" | "down";
}

function PageTransition({ children, direction = "right" }: PageTransitionProps) {
  const directions = {
    left: { initial: { x: -300 }, exit: { x: 300 } },
    right: { initial: { x: 300 }, exit: { x: -300 } },
    up: { initial: { y: -300 }, exit: { y: 300 } },
    down: { initial: { y: 300 }, exit: { y: -300 } },
  };

  const { initial, exit } = directions[direction];

  return (
    <motion.div
      initial={{ ...initial, opacity: 0 }}
      animate={{ x: 0, y: 0, opacity: 1 }}
      exit={{ ...exit, opacity: 0 }}
      transition={{
        type: "spring",
        stiffness: 260,
        damping: 20,
      }}
    >
      {children}
    </motion.div>
  );
}

// Shared layout animation for tabs/cards
interface Tab {
  id: string;
  label: string;
  content: React.ReactNode;
}

function AnimatedTabs({ tabs }: { tabs: Tab[] }) {
  const [activeTab, setActiveTab] = React.useState(tabs[0].id);

  return (
    <div>
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="relative px-4 py-2 text-sm font-medium rounded-md transition-colors"
            style={{ color: activeTab === tab.id ? "#fff" : "#6b7280" }}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId="activeTab"
                className="absolute inset-0 bg-blue-600 rounded-md"
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                style={{ zIndex: -1 }}
              />
            )}
            {tab.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.15 }}
          className="mt-4"
        >
          {tabs.find((t) => t.id === activeTab)?.content}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// Expandable card with layout animation
interface ExpandableCardProps {
  id: string;
  title: string;
  summary: string;
  children: React.ReactNode;
  image?: string;
}

function ExpandableCard({ id, title, summary, children, image }: ExpandableCardProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  return (
    <motion.div
      layout
      onClick={() => setIsExpanded(!isExpanded)}
      className="bg-white rounded-xl shadow-lg overflow-hidden cursor-pointer"
      style={{ borderRadius: 16 }}
      whileHover={{ scale: isExpanded ? 1 : 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      <motion.div layout="position" className="p-6">
        {image && (
          <motion.img
            layout
            src={image}
            alt=""
            className={`rounded-lg object-cover mb-4 ${
              isExpanded ? "w-full h-64" : "w-20 h-20 float-left mr-4"
            }`}
          />
        )}
        <motion.h3 layout="position" className="text-xl font-bold">
          {title}
        </motion.h3>
        <motion.p layout="position" className="text-gray-500 mt-1">
          {summary}
        </motion.p>
      </motion.div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="px-6 pb-6"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// Notification toast with animation
interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

function ToastContainer({ toasts, onDismiss }: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 50, scale: 0.3 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5, transition: { duration: 0.2 } }}
            className={`px-4 py-3 rounded-lg shadow-lg min-w-[300px] flex justify-between items-center ${
              toast.type === "success"
                ? "bg-green-500 text-white"
                : toast.type === "error"
                ? "bg-red-500 text-white"
                : "bg-blue-500 text-white"
            }`}
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            onDragEnd={(_, info) => {
              if (Math.abs(info.offset.x) > 100) {
                onDismiss(toast.id);
              }
            }}
          >
            <span>{toast.message}</span>
            <button
              onClick={() => onDismiss(toast.id)}
              className="ml-4 text-white/80 hover:text-white"
            >
              x
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

import React from "react";

export { AnimatedList, PageTransition, AnimatedTabs, ExpandableCard, ToastContainer };
'''),

    ("react/animation_css_transitions", r'''Build CSS-only animation patterns for React components including smooth transitions, keyframe animations, and a transition group component that handles enter/exit animations without Framer Motion.''', r'''// components/Transition.tsx - CSS-based animation system
import React, { useState, useEffect, useRef, useCallback } from "react";

type TransitionState = "entering" | "entered" | "exiting" | "exited";

interface TransitionProps {
  show: boolean;
  children: React.ReactNode | ((state: TransitionState) => React.ReactNode);
  enter?: string;       // CSS classes during enter
  enterFrom?: string;   // CSS classes at enter start
  enterTo?: string;     // CSS classes at enter end
  leave?: string;       // CSS classes during leave
  leaveFrom?: string;   // CSS classes at leave start
  leaveTo?: string;     // CSS classes at leave end
  duration?: number;
  unmountOnExit?: boolean;
  onEntered?: () => void;
  onExited?: () => void;
}

function Transition({
  show,
  children,
  enter = "transition-all duration-300 ease-out",
  enterFrom = "opacity-0 translate-y-4",
  enterTo = "opacity-100 translate-y-0",
  leave = "transition-all duration-200 ease-in",
  leaveFrom = "opacity-100 translate-y-0",
  leaveTo = "opacity-0 translate-y-4",
  duration = 300,
  unmountOnExit = true,
  onEntered,
  onExited,
}: TransitionProps) {
  const [state, setState] = useState<TransitionState>(show ? "entered" : "exited");
  const [mounted, setMounted] = useState(show);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    if (show) {
      setMounted(true);
      // Force a reflow before applying enter classes
      requestAnimationFrame(() => {
        setState("entering");
        timeoutRef.current = setTimeout(() => {
          setState("entered");
          onEntered?.();
        }, duration);
      });
    } else if (state !== "exited") {
      setState("exiting");
      timeoutRef.current = setTimeout(() => {
        setState("exited");
        if (unmountOnExit) setMounted(false);
        onExited?.();
      }, duration);
    }

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [show, duration, unmountOnExit, onEntered, onExited]);

  if (!mounted) return null;

  const className = (() => {
    switch (state) {
      case "entering":
        return `${enter} ${enterTo}`;
      case "entered":
        return enterTo;
      case "exiting":
        return `${leave} ${leaveTo}`;
      case "exited":
        return enterFrom;
      default:
        return "";
    }
  })();

  if (typeof children === "function") {
    return <>{children(state)}</>;
  }

  return <div className={className}>{children}</div>;
}

// Transition group for list animations
interface TransitionGroupProps {
  children: React.ReactNode;
  className?: string;
}

function TransitionGroup({ children, className }: TransitionGroupProps) {
  const childrenArray = React.Children.toArray(children);

  return (
    <div className={className}>
      {childrenArray.map((child, index) => {
        if (!React.isValidElement(child)) return child;

        return React.cloneElement(child as React.ReactElement<any>, {
          style: {
            ...((child as React.ReactElement<any>).props.style || {}),
            animationDelay: `${index * 50}ms`,
          },
        });
      })}
    </div>
  );
}

// CSS animation presets
const animations = {
  fadeIn: {
    enter: "transition-opacity duration-300 ease-out",
    enterFrom: "opacity-0",
    enterTo: "opacity-100",
    leave: "transition-opacity duration-200 ease-in",
    leaveFrom: "opacity-100",
    leaveTo: "opacity-0",
  },
  slideUp: {
    enter: "transition-all duration-300 ease-out",
    enterFrom: "opacity-0 translate-y-8",
    enterTo: "opacity-100 translate-y-0",
    leave: "transition-all duration-200 ease-in",
    leaveFrom: "opacity-100 translate-y-0",
    leaveTo: "opacity-0 translate-y-8",
  },
  slideDown: {
    enter: "transition-all duration-300 ease-out",
    enterFrom: "opacity-0 -translate-y-8",
    enterTo: "opacity-100 translate-y-0",
    leave: "transition-all duration-200 ease-in",
    leaveFrom: "opacity-100 translate-y-0",
    leaveTo: "opacity-0 -translate-y-8",
  },
  slideLeft: {
    enter: "transition-all duration-300 ease-out",
    enterFrom: "opacity-0 translate-x-8",
    enterTo: "opacity-100 translate-x-0",
    leave: "transition-all duration-200 ease-in",
    leaveFrom: "opacity-100 translate-x-0",
    leaveTo: "opacity-0 translate-x-8",
  },
  scaleIn: {
    enter: "transition-all duration-300 ease-out",
    enterFrom: "opacity-0 scale-95",
    enterTo: "opacity-100 scale-100",
    leave: "transition-all duration-200 ease-in",
    leaveFrom: "opacity-100 scale-100",
    leaveTo: "opacity-0 scale-95",
  },
  collapse: {
    enter: "transition-all duration-300 ease-out overflow-hidden",
    enterFrom: "opacity-0 max-h-0",
    enterTo: "opacity-100 max-h-screen",
    leave: "transition-all duration-200 ease-in overflow-hidden",
    leaveFrom: "opacity-100 max-h-screen",
    leaveTo: "opacity-0 max-h-0",
  },
};

// Accordion with CSS transitions
function Accordion({
  items,
}: {
  items: Array<{ id: string; title: string; content: React.ReactNode }>;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const isOpen = openId === item.id;
        return (
          <div key={item.id} className="border rounded-lg overflow-hidden">
            <button
              onClick={() => setOpenId(isOpen ? null : item.id)}
              className="w-full px-4 py-3 text-left font-medium flex justify-between items-center hover:bg-gray-50"
              aria-expanded={isOpen}
            >
              {item.title}
              <span
                className={`transform transition-transform duration-200 ${
                  isOpen ? "rotate-180" : ""
                }`}
              >
                v
              </span>
            </button>
            <Transition show={isOpen} {...animations.collapse} duration={300}>
              <div className="px-4 pb-4 text-gray-600">{item.content}</div>
            </Transition>
          </div>
        );
      })}
    </div>
  );
}

// Modal with backdrop animation
function AnimatedModal({
  isOpen,
  onClose,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <Transition show={isOpen} {...animations.fadeIn} duration={200}>
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={onClose}
          aria-hidden="true"
        />
      </Transition>
      <Transition show={isOpen} {...animations.scaleIn} duration={300}>
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-auto"
            role="dialog"
            aria-modal="true"
          >
            {children}
          </div>
        </div>
      </Transition>
    </>
  );
}

// Skeleton loading with shimmer animation
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`bg-gray-200 rounded animate-pulse ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.5s infinite",
      }}
    />
  );
}

// CSS keyframes (would be in global CSS or a style tag)
// @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

export { Transition, TransitionGroup, animations, Accordion, AnimatedModal, Skeleton };
'''),

    ("react/animation_scroll", r'''Build scroll-based animation patterns in React using Intersection Observer and scroll position tracking, including reveal-on-scroll, parallax effects, and scroll progress indicators.''', r'''// hooks/useScrollAnimation.ts
import { useState, useEffect, useRef, useCallback, useMemo } from "react";

// Hook: Detect when element is in viewport
interface UseInViewOptions {
  threshold?: number | number[];
  rootMargin?: string;
  triggerOnce?: boolean;
}

function useInView(options: UseInViewOptions = {}): [React.RefObject<HTMLDivElement>, boolean, number] {
  const { threshold = 0.1, rootMargin = "0px", triggerOnce = false } = options;
  const ref = useRef<HTMLDivElement>(null);
  const [isInView, setIsInView] = useState(false);
  const [ratio, setRatio] = useState(0);
  const triggered = useRef(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        const visible = entry.isIntersecting;
        setRatio(entry.intersectionRatio);

        if (triggerOnce && triggered.current) return;

        setIsInView(visible);
        if (visible && triggerOnce) {
          triggered.current = true;
          observer.disconnect();
        }
      },
      { threshold, rootMargin }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [threshold, rootMargin, triggerOnce]);

  return [ref, isInView, ratio];
}

// Hook: Track scroll position
function useScrollPosition(): { x: number; y: number; direction: "up" | "down" | null } {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [direction, setDirection] = useState<"up" | "down" | null>(null);
  const prevY = useRef(0);

  useEffect(() => {
    let ticking = false;

    const handleScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const y = window.scrollY;
          setPosition({ x: window.scrollX, y });
          setDirection(y > prevY.current ? "down" : y < prevY.current ? "up" : null);
          prevY.current = y;
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return { ...position, direction };
}

// Hook: Page scroll progress (0 to 1)
function useScrollProgress(): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const winHeight = window.innerHeight;
      const docHeight = document.documentElement.scrollHeight;
      const scrollTop = window.scrollY;
      const scrollable = docHeight - winHeight;
      setProgress(scrollable > 0 ? scrollTop / scrollable : 0);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return progress;
}

// Component: Reveal on scroll
interface RevealProps {
  children: React.ReactNode;
  animation?: "fadeUp" | "fadeDown" | "fadeLeft" | "fadeRight" | "scaleIn" | "none";
  delay?: number;
  duration?: number;
  threshold?: number;
  className?: string;
}

function Reveal({
  children,
  animation = "fadeUp",
  delay = 0,
  duration = 600,
  threshold = 0.1,
  className = "",
}: RevealProps) {
  const [ref, isInView] = useInView({ threshold, triggerOnce: true });

  const animationStyles = useMemo(() => {
    const base: React.CSSProperties = {
      transition: `all ${duration}ms ease-out ${delay}ms`,
    };

    const hidden: Record<string, React.CSSProperties> = {
      fadeUp: { opacity: 0, transform: "translateY(40px)" },
      fadeDown: { opacity: 0, transform: "translateY(-40px)" },
      fadeLeft: { opacity: 0, transform: "translateX(40px)" },
      fadeRight: { opacity: 0, transform: "translateX(-40px)" },
      scaleIn: { opacity: 0, transform: "scale(0.9)" },
      none: { opacity: 0 },
    };

    const visible: React.CSSProperties = {
      opacity: 1,
      transform: "translate(0) scale(1)",
    };

    return {
      ...base,
      ...(isInView ? visible : hidden[animation]),
    };
  }, [isInView, animation, delay, duration]);

  return (
    <div ref={ref} style={animationStyles} className={className}>
      {children}
    </div>
  );
}

// Component: Scroll progress bar
function ScrollProgressBar({ color = "#3b82f6", height = 3 }: {
  color?: string;
  height?: number;
}) {
  const progress = useScrollProgress();

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(progress * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        style={{
          width: `${progress * 100}%`,
          height: "100%",
          backgroundColor: color,
          transition: "width 100ms ease-out",
        }}
      />
    </div>
  );
}

// Component: Parallax section
interface ParallaxProps {
  children: React.ReactNode;
  speed?: number; // -1 to 1, negative = slower, positive = faster
  className?: string;
}

function Parallax({ children, speed = 0.5, className = "" }: ParallaxProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      if (!ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      const windowHeight = window.innerHeight;
      const elementCenter = rect.top + rect.height / 2;
      const viewportCenter = windowHeight / 2;
      const distance = elementCenter - viewportCenter;
      setOffset(distance * speed * -0.5);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, [speed]);

  return (
    <div ref={ref} className={`overflow-hidden ${className}`}>
      <div
        style={{
          transform: `translateY(${offset}px)`,
          willChange: "transform",
        }}
      >
        {children}
      </div>
    </div>
  );
}

// Component: Sticky header that hides on scroll down
function StickyHeader({ children }: { children: React.ReactNode }) {
  const { direction, y } = useScrollPosition();
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    if (y < 100) {
      setIsVisible(true);
    } else if (direction === "down") {
      setIsVisible(false);
    } else if (direction === "up") {
      setIsVisible(true);
    }
  }, [y, direction]);

  return (
    <header
      className="fixed top-0 left-0 right-0 z-40 bg-white shadow transition-transform duration-300"
      style={{
        transform: isVisible ? "translateY(0)" : "translateY(-100%)",
      }}
    >
      {children}
    </header>
  );
}

// Component: Staggered reveal for grid items
function StaggeredGrid({
  children,
  staggerDelay = 100,
  animation = "fadeUp" as const,
}: {
  children: React.ReactNode;
  staggerDelay?: number;
  animation?: "fadeUp" | "scaleIn";
}) {
  const childArray = React.Children.toArray(children);

  return (
    <>
      {childArray.map((child, index) => (
        <Reveal
          key={index}
          animation={animation}
          delay={index * staggerDelay}
          threshold={0.05}
        >
          {child}
        </Reveal>
      ))}
    </>
  );
}

import React from "react";

export {
  useInView,
  useScrollPosition,
  useScrollProgress,
  Reveal,
  ScrollProgressBar,
  Parallax,
  StickyHeader,
  StaggeredGrid,
};
'''),

    ("react/animation_gestures", r'''Build gesture-based interaction patterns in React including swipeable cards, drag-to-reorder lists, pinch-to-zoom on images, and long-press context menus.''', r'''// hooks/useGesture.ts
import React, { useState, useRef, useCallback, useEffect } from "react";

// Types for gesture tracking
interface Point { x: number; y: number; }
interface GestureState {
  startPoint: Point;
  currentPoint: Point;
  delta: Point;
  velocity: Point;
  direction: "left" | "right" | "up" | "down" | null;
  distance: number;
  isActive: boolean;
}

// Swipeable card component
interface SwipeableCardProps {
  children: React.ReactNode;
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold?: number;
  className?: string;
}

function SwipeableCard({
  children,
  onSwipeLeft,
  onSwipeRight,
  threshold = 100,
  className = "",
}: SwipeableCardProps) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const startPos = useRef<Point>({ x: 0, y: 0 });
  const elementRef = useRef<HTMLDivElement>(null);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    setIsDragging(true);
    startPos.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - startPos.current.x;
      const dy = (e.clientY - startPos.current.y) * 0.3; // Dampen vertical movement
      setOffset({ x: dx, y: dy });
    },
    [isDragging]
  );

  const handlePointerUp = useCallback(() => {
    setIsDragging(false);

    if (Math.abs(offset.x) > threshold) {
      // Swipe detected - animate out
      setIsExiting(true);
      const direction = offset.x > 0 ? "right" : "left";
      const exitX = direction === "right" ? 500 : -500;

      setOffset({ x: exitX, y: offset.y });

      setTimeout(() => {
        if (direction === "left") onSwipeLeft?.();
        else onSwipeRight?.();
        setOffset({ x: 0, y: 0 });
        setIsExiting(false);
      }, 300);
    } else {
      // Snap back
      setOffset({ x: 0, y: 0 });
    }
  }, [offset, threshold, onSwipeLeft, onSwipeRight]);

  const rotation = offset.x * 0.05; // Rotate based on horizontal offset
  const opacity = isExiting ? 0 : 1 - Math.abs(offset.x) / 500;

  return (
    <div
      ref={elementRef}
      className={`touch-none select-none ${className}`}
      style={{
        transform: `translate(${offset.x}px, ${offset.y}px) rotate(${rotation}deg)`,
        opacity: Math.max(0.3, opacity),
        transition: isDragging ? "none" : "all 0.3s ease-out",
        cursor: isDragging ? "grabbing" : "grab",
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      {/* Swipe indicator */}
      {isDragging && Math.abs(offset.x) > 30 && (
        <div
          className={`absolute top-4 ${
            offset.x > 0 ? "right-4 text-green-500" : "left-4 text-red-500"
          } text-2xl font-bold transform rotate-12`}
        >
          {offset.x > 0 ? "LIKE" : "NOPE"}
        </div>
      )}
      {children}
    </div>
  );
}

// Drag-to-reorder list
interface DragItem {
  id: string;
  content: React.ReactNode;
}

function DragReorderList({
  items,
  onReorder,
  className = "",
}: {
  items: DragItem[];
  onReorder: (items: DragItem[]) => void;
  className?: string;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState(0);
  const itemRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const startY = useRef(0);

  const handleDragStart = useCallback((index: number, e: React.PointerEvent) => {
    setDragIndex(index);
    startY.current = e.clientY;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const handleDragMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragIndex === null) return;
      const dy = e.clientY - startY.current;
      setDragOffset(dy);

      // Determine hover position
      const itemHeight = 60; // Approximate item height
      const steps = Math.round(dy / itemHeight);
      const newIndex = Math.max(0, Math.min(items.length - 1, dragIndex + steps));
      setHoverIndex(newIndex);
    },
    [dragIndex, items.length]
  );

  const handleDragEnd = useCallback(() => {
    if (dragIndex !== null && hoverIndex !== null && dragIndex !== hoverIndex) {
      const newItems = [...items];
      const [moved] = newItems.splice(dragIndex, 1);
      newItems.splice(hoverIndex, 0, moved);
      onReorder(newItems);
    }

    setDragIndex(null);
    setHoverIndex(null);
    setDragOffset(0);
  }, [dragIndex, hoverIndex, items, onReorder]);

  return (
    <div
      className={className}
      onPointerMove={handleDragMove}
      onPointerUp={handleDragEnd}
    >
      {items.map((item, index) => {
        const isDragging = index === dragIndex;
        const isHovered = hoverIndex !== null && dragIndex !== null;

        let translateY = 0;
        if (isHovered && !isDragging && dragIndex !== null && hoverIndex !== null) {
          if (index > dragIndex && index <= hoverIndex) {
            translateY = -60;
          } else if (index < dragIndex && index >= hoverIndex) {
            translateY = 60;
          }
        }

        return (
          <div
            key={item.id}
            ref={(el) => { if (el) itemRefs.current.set(item.id, el); }}
            className={`flex items-center gap-3 p-3 bg-white rounded-lg mb-2 ${
              isDragging ? "shadow-lg z-10 relative" : "shadow-sm"
            }`}
            style={{
              transform: isDragging
                ? `translateY(${dragOffset}px) scale(1.02)`
                : `translateY(${translateY}px)`,
              transition: isDragging ? "none" : "transform 200ms ease",
              opacity: isDragging ? 0.9 : 1,
            }}
          >
            {/* Drag handle */}
            <div
              className="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 px-1"
              onPointerDown={(e) => handleDragStart(index, e)}
              style={{ touchAction: "none" }}
            >
              :::
            </div>
            <div className="flex-1">{item.content}</div>
          </div>
        );
      })}
    </div>
  );
}

// Long press hook
function useLongPress(
  callback: () => void,
  options: { delay?: number; onStart?: () => void; onCancel?: () => void } = {}
) {
  const { delay = 500, onStart, onCancel } = options;
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const start = useCallback(
    (e: React.PointerEvent | React.TouchEvent) => {
      e.preventDefault();
      onStart?.();
      timeoutRef.current = setTimeout(() => {
        callbackRef.current();
      }, delay);
    },
    [delay, onStart]
  );

  const cancel = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    onCancel?.();
  }, [onCancel]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return {
    onPointerDown: start,
    onPointerUp: cancel,
    onPointerLeave: cancel,
    onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
  };
}

// Long press context menu component
function LongPressMenu({
  children,
  menuItems,
}: {
  children: React.ReactNode;
  menuItems: Array<{ label: string; onClick: () => void; destructive?: boolean }>;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  const longPressHandlers = useLongPress(
    () => setIsOpen(true),
    {
      delay: 500,
      onStart: () => {
        // Could add haptic feedback here
      },
    }
  );

  return (
    <div className="relative" {...longPressHandlers}>
      {children}
      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div
            className="absolute z-50 bg-white rounded-lg shadow-xl border py-1 min-w-[160px]"
            style={{ top: "100%", left: 0 }}
          >
            {menuItems.map((item, i) => (
              <button
                key={i}
                onClick={() => {
                  item.onClick();
                  setIsOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-100 ${
                  item.destructive ? "text-red-600" : "text-gray-700"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export { SwipeableCard, DragReorderList, useLongPress, LongPressMenu };
'''),

    ("react/animation_layout", r'''Build layout animation patterns in React including animated grid reflows, smooth height transitions for collapsible content, and morphing between different layout states.''', r'''// components/LayoutAnimations.tsx
import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";

// Hook: Animate height changes for collapsible content
function useAnimatedHeight<T extends HTMLElement>(): [
  React.RefObject<T>,
  { height: string; overflow: string; transition: string }
] {
  const ref = useRef<T>(null);
  const [style, setStyle] = useState({
    height: "auto",
    overflow: "hidden",
    transition: "height 300ms ease",
  });
  const prevHeight = useRef<number>(0);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const newHeight = entry.contentRect.height;
        if (prevHeight.current !== 0 && prevHeight.current !== newHeight) {
          // Animate from previous height to new height
          element.style.height = `${prevHeight.current}px`;
          requestAnimationFrame(() => {
            element.style.height = `${newHeight}px`;
          });

          // After transition, set back to auto
          const onTransitionEnd = () => {
            element.style.height = "auto";
            element.removeEventListener("transitionend", onTransitionEnd);
          };
          element.addEventListener("transitionend", onTransitionEnd);
        }
        prevHeight.current = newHeight;
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, style];
}

// FLIP animation utility (First, Last, Invert, Play)
interface FlipState {
  id: string;
  rect: DOMRect;
}

function useFlipAnimation(items: string[]) {
  const positionsRef = useRef<Map<string, DOMRect>>(new Map());
  const elementsRef = useRef<Map<string, HTMLElement>>(new Map());

  // Capture current positions (First)
  const capturePositions = useCallback(() => {
    const positions = new Map<string, DOMRect>();
    for (const [id, element] of elementsRef.current) {
      positions.set(id, element.getBoundingClientRect());
    }
    positionsRef.current = positions;
  }, []);

  // Animate from old positions to new positions (Invert + Play)
  const animate = useCallback(() => {
    requestAnimationFrame(() => {
      for (const [id, element] of elementsRef.current) {
        const firstRect = positionsRef.current.get(id);
        if (!firstRect) continue;

        const lastRect = element.getBoundingClientRect();

        // Calculate the inversion
        const deltaX = firstRect.left - lastRect.left;
        const deltaY = firstRect.top - lastRect.top;
        const deltaW = firstRect.width / lastRect.width;
        const deltaH = firstRect.height / lastRect.height;

        if (deltaX === 0 && deltaY === 0 && deltaW === 1 && deltaH === 1) {
          continue;
        }

        // Apply inversion
        element.style.transform = `translate(${deltaX}px, ${deltaY}px) scale(${deltaW}, ${deltaH})`;
        element.style.transition = "none";

        // Play animation
        requestAnimationFrame(() => {
          element.style.transform = "";
          element.style.transition = "transform 300ms ease";
        });
      }
    });
  }, []);

  const registerElement = useCallback((id: string, element: HTMLElement | null) => {
    if (element) {
      elementsRef.current.set(id, element);
    } else {
      elementsRef.current.delete(id);
    }
  }, []);

  return { capturePositions, animate, registerElement };
}

// Animated grid that smoothly reflows when items change
interface GridItem {
  id: string;
  content: React.ReactNode;
  size?: "small" | "medium" | "large";
}

function AnimatedGrid({
  items,
  columns = 3,
  gap = 16,
}: {
  items: GridItem[];
  columns?: number;
  gap?: number;
}) {
  const { capturePositions, animate, registerElement } = useFlipAnimation(
    items.map((i) => i.id)
  );

  // Capture positions before update
  useLayoutEffect(() => {
    capturePositions();
  });

  // Animate after update
  useEffect(() => {
    animate();
  }, [items, animate]);

  const sizeClasses = {
    small: "col-span-1",
    medium: "col-span-1 md:col-span-2",
    large: "col-span-1 md:col-span-2 lg:col-span-3",
  };

  return (
    <div
      className="grid"
      style={{
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: `${gap}px`,
      }}
    >
      {items.map((item) => (
        <div
          key={item.id}
          ref={(el) => registerElement(item.id, el)}
          className={`bg-white rounded-lg shadow p-4 ${sizeClasses[item.size || "small"]}`}
        >
          {item.content}
        </div>
      ))}
    </div>
  );
}

// Collapsible section with smooth height animation
function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<string>(defaultOpen ? "auto" : "0");

  useEffect(() => {
    if (!contentRef.current) return;

    if (isOpen) {
      const contentHeight = contentRef.current.scrollHeight;
      setHeight(`${contentHeight}px`);

      const timer = setTimeout(() => setHeight("auto"), 300);
      return () => clearTimeout(timer);
    } else {
      // First set explicit height, then collapse
      const contentHeight = contentRef.current.scrollHeight;
      setHeight(`${contentHeight}px`);
      requestAnimationFrame(() => {
        setHeight("0");
      });
    }
  }, [isOpen]);

  return (
    <div className="border rounded-lg">
      <button
        className="w-full px-4 py-3 flex justify-between items-center font-medium hover:bg-gray-50"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        {title}
        <span
          className="transform transition-transform duration-300"
          style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0deg)" }}
        >
          v
        </span>
      </button>
      <div
        ref={contentRef}
        style={{
          height,
          overflow: "hidden",
          transition: "height 300ms ease",
        }}
      >
        <div className="px-4 pb-4">{children}</div>
      </div>
    </div>
  );
}

// View transition: morph between two layout states
function LayoutMorph({
  layout,
  children,
}: {
  layout: "grid" | "list";
  children: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Use FLIP on layout change
  const prevLayout = useRef(layout);

  useLayoutEffect(() => {
    if (prevLayout.current === layout) return;
    prevLayout.current = layout;

    const container = containerRef.current;
    if (!container) return;

    // Capture first positions
    const children = Array.from(container.children) as HTMLElement[];
    const firstPositions = children.map((child) => child.getBoundingClientRect());

    // Force layout recalculation
    requestAnimationFrame(() => {
      children.forEach((child, index) => {
        const last = child.getBoundingClientRect();
        const first = firstPositions[index];
        if (!first) return;

        const dx = first.left - last.left;
        const dy = first.top - last.top;

        child.style.transform = `translate(${dx}px, ${dy}px)`;
        child.style.transition = "none";

        requestAnimationFrame(() => {
          child.style.transform = "";
          child.style.transition = "transform 400ms cubic-bezier(0.4, 0, 0.2, 1)";
        });
      });
    });
  }, [layout]);

  return (
    <div
      ref={containerRef}
      className={`transition-all duration-300 ${
        layout === "grid"
          ? "grid grid-cols-2 md:grid-cols-3 gap-4"
          : "flex flex-col gap-2"
      }`}
    >
      {children}
    </div>
  );
}

export {
  useAnimatedHeight,
  useFlipAnimation,
  AnimatedGrid,
  CollapsibleSection,
  LayoutMorph,
};
'''),
]
