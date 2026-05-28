// vue-virtual-scroller 2.x ships no type definitions. Declare the slice of
// the API this app uses: DynamicScroller (variable-height windowed list) and
// its DynamicScrollerItem wrapper. Props are loosely typed because the
// library's runtime accepts more than we pass.
declare module 'vue-virtual-scroller' {
  import type { DefineComponent } from 'vue'

  export const RecycleScroller: DefineComponent<Record<string, unknown>>
  export const DynamicScroller: DefineComponent<{
    items: unknown[]
    minItemSize: number
    keyField?: string
  }> & {
    scrollToItem: (index: number) => void
  }
  export const DynamicScrollerItem: DefineComponent<{
    item: unknown
    active: boolean
    sizeDependencies?: unknown[]
    dataIndex?: number
  }>
}

declare module 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
