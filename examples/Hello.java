public class Hello {
    String name;

    public Hello(String name) {
        this.name = name;
    }

    public String greet(String other) {
        String prefix = this.name + " -> ";
        return prefix + other;
    }
}
