export interface SkillGroup { label: string; items: string[] }
export interface PrintSkillsProps {
  groups: SkillGroup[];
}
export declare function PrintSkills(props: PrintSkillsProps): JSX.Element;
