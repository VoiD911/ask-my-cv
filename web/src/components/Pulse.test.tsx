import { render, screen } from "@testing-library/react";
import { Pulse } from "./Pulse";

function inSvg(node: React.ReactNode) {
  return render(<svg>{node}</svg>);
}

describe("Pulse", () => {
  it("fait voyager une impulsion le long de la piste", () => {
    inSvg(<Pulse d="M 0 0 L 10 0" mode="travel" />);
    const pulse = screen.getByTestId("pulse");
    const paths = pulse.querySelectorAll("path");
    expect(paths).toHaveLength(2);
    for (const path of paths) {
      expect(path).toHaveAttribute("d", "M 0 0 L 10 0");
      expect(path).toHaveAttribute("pathLength", "100");
    }
  });

  it("ne dessine rien en mouvement réduit", () => {
    const { container } = inSvg(<Pulse d="M 0 0 L 10 0" mode="travel" reducedMotion />);
    expect(container.querySelector("g")).toBeNull();
  });

  it("s'arrête sur un point fixe au bout de la piste, même en mouvement réduit", () => {
    inSvg(<Pulse d="M 0 0 L 10 0" mode="halt" end={{ x: 10, y: 0 }} reducedMotion />);
    const dots = screen.getByTestId("pulse-halt").querySelectorAll("circle");
    expect(dots).toHaveLength(2);
    expect(dots[1]).toHaveAttribute("cx", "10");
    expect(screen.queryByTestId("pulse")).toBeNull();
  });
});
