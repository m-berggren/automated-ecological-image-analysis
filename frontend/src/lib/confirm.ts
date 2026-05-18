import { reactive } from 'vue'

export type ConfirmVariant = 'danger' | 'default'

export interface ConfirmOptions {
  title?: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: ConfirmVariant
}

export interface AlertOptions {
  title?: string
  message: string
  confirmLabel?: string
  variant?: ConfirmVariant
}

interface ConfirmState extends Required<ConfirmOptions> {
  open: boolean
  alertOnly: boolean
  resolve: ((value: boolean) => void) | null
}

// Single shared dialog: only one prompt is ever live at a time. A second
// confirm() while one is open auto-dismisses the first as cancelled.
const state = reactive<ConfirmState>({
  open: false,
  title: '',
  message: '',
  confirmLabel: 'Confirm',
  cancelLabel: 'Cancel',
  variant: 'default',
  alertOnly: false,
  resolve: null,
})

export function confirmState(): ConfirmState {
  return state
}

export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (state.resolve) state.resolve(false)
  state.title = options.title ?? ''
  state.message = options.message
  state.confirmLabel = options.confirmLabel ?? 'Confirm'
  state.cancelLabel = options.cancelLabel ?? 'Cancel'
  state.variant = options.variant ?? 'default'
  state.alertOnly = false
  state.open = true
  return new Promise<boolean>((resolve) => {
    state.resolve = resolve
  })
}

export function alert(options: AlertOptions): Promise<void> {
  if (state.resolve) state.resolve(false)
  state.title = options.title ?? ''
  state.message = options.message
  state.confirmLabel = options.confirmLabel ?? 'OK'
  state.cancelLabel = ''
  state.variant = options.variant ?? 'default'
  state.alertOnly = true
  state.open = true
  return new Promise<void>((resolve) => {
    state.resolve = () => resolve()
  })
}

export function resolveConfirm(value: boolean): void {
  if (state.resolve) {
    state.resolve(value)
    state.resolve = null
  }
  state.open = false
}
