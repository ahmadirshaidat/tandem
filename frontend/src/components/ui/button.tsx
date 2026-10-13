import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
const buttonVariants = cva("button", {
  variants: {
    variant: {
      primary: "button-primary",
      secondary: "button-secondary",
      ghost: "button-ghost",
      danger: "button-danger",
    },
  },
  defaultVariants: { variant: "primary" },
});
export function Button({
  className,
  variant,
  asChild = false,
  type = "button",
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      type={asChild ? undefined : type}
      className={cn(buttonVariants({ variant }), className)}
      {...props}
    />
  );
}
