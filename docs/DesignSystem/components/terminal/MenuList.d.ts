export interface MenuEntry { icon: string; title: string; desc: string }
export interface MenuListProps {
  items: MenuEntry[];
  active?: number;
  onSelect?: (index: number) => void;
}
export declare function MenuList(props: MenuListProps): JSX.Element;
