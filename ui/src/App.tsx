/**
 * Standalone App - Complete application with router for standalone usage
 *
 * This is useful for:
 * - Local development
 * - Testing the UI independently
 * - Running as a standalone application
 */

import { BrowserRouter } from 'react-router-dom'
import { IntegrationsMicroFrontend } from './MicroFrontend'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        {/* Simple header for standalone mode */}
        <header className="border-b bg-card">
          <div className="container mx-auto px-4 py-3">
            <h1 className="text-xl font-bold">Integrations</h1>
          </div>
        </header>

        {/* Main content */}
        <main className="container mx-auto px-4 py-6">
          <IntegrationsMicroFrontend />
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
