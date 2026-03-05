import * as React from "react"
import { createContext, useContext, useState } from "react"
import { cn } from "@/lib/utils"

// ─── Context ────────────────────────────────────────────────────

interface TabsContextValue {
  activeTab: string
  setActiveTab: (tab: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

function useTabsContext() {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error("Tabs components must be used within <Tabs>")
  return ctx
}

// ─── Tabs (root) ────────────────────────────────────────────────

interface TabsProps {
  defaultTab: string
  children: React.ReactNode
  className?: string
}

function Tabs({ defaultTab, children, className }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab)

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

// ─── TabsList ───────────────────────────────────────────────────

const TabsList = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    role="tablist"
    className={cn("flex border-b", className)}
    {...props}
  />
))
TabsList.displayName = "TabsList"

// ─── TabsTrigger ────────────────────────────────────────────────

interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string
}

const TabsTrigger = React.forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ value, className, ...props }, ref) => {
    const { activeTab, setActiveTab } = useTabsContext()
    const isActive = activeTab === value

    return (
      <button
        ref={ref}
        role="tab"
        aria-selected={isActive}
        className={cn(
          "px-4 py-2 text-sm font-medium transition-colors -mb-px",
          isActive
            ? "text-foreground border-b-2 border-primary"
            : "text-muted-foreground hover:text-foreground",
          className
        )}
        onClick={() => setActiveTab(value)}
        {...props}
      />
    )
  }
)
TabsTrigger.displayName = "TabsTrigger"

// ─── TabsContent ────────────────────────────────────────────────

interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string
}

const TabsContent = React.forwardRef<HTMLDivElement, TabsContentProps>(
  ({ value, className, children, ...props }, ref) => {
    const { activeTab } = useTabsContext()
    if (activeTab !== value) return null

    return (
      <div
        ref={ref}
        role="tabpanel"
        className={cn("pt-6", className)}
        {...props}
      >
        {children}
      </div>
    )
  }
)
TabsContent.displayName = "TabsContent"

export { Tabs, TabsList, TabsTrigger, TabsContent }
