// Sonner toaster, kept separate so the app shell stays tiny.
import { Toaster } from 'sonner'

export function AppToaster() {
  return (
    <Toaster
      position="top-center"
      offset={72}
      mobileOffset={{ top: 72 }}
      visibleToasts={3}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast: 'hh-toast',
          title: 'hh-toast-title',
          description: 'hh-toast-desc',
          actionButton: 'hh-toast-action',
          error: 'hh-toast-error',
          success: 'hh-toast-success',
          warning: 'hh-toast-warning',
          icon: 'hh-toast-icon',
        },
      }}
    />
  )
}

